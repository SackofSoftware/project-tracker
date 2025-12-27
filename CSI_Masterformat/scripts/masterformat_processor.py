import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import json
import requests
from datetime import datetime
import threading
import os
import PyPDF2
import time

CHARS_PER_TOKEN = 4  # conservative estimate

CONTEXT_PRESETS = [4096, 8192, 16384, 24000, 32000, 40000, 64000, 128000]
PROCESSING_MODES = ["Per Page", "Whole File", "Chunked"]

class MasterformatProcessor:
    def __init__(self, root):
        self.root = root
        self.root.title("Masterformat Batch Processor - Ollama (Modes + Context Toggle)")
        self.root.geometry("1700x1050")

        # Ollama server settings
        self.ollama_host = tk.StringVar(value="http://10.0.0.36:11434")
        self.ollama_url = f"{self.ollama_host.get()}/api/generate"

        # Models
        self.qwen_models = self._fetch_models()
        self.selected_model = tk.StringVar(value=self.qwen_models[0] if self.qwen_models else "")

        # JSON Mode setting
        self.json_mode = tk.StringVar(value="prompt_only")  # default to the mode that's been working

        # Batch processing settings - use environment variable
        masterformat_dir = os.getenv("MASTERFORMAT_DIR", "")
        self.base_dir = os.path.join(masterformat_dir, "Divisions") if masterformat_dir else ""
        self.output_dir = os.path.join(self.base_dir, "page_json")
        os.makedirs(self.output_dir, exist_ok=True)

        self.processing = False
        self.paused = False

        # Context window (tokens)
        self.context_tokens = tk.IntVar(value=8192)
        # Output allowance (tokens) to budget for model's response (incl. "thinking")
        self.output_tokens = tk.IntVar(value=3000)
        # Safety overhead (prompt + buffer tokens)
        self.prompt_overhead_tokens = tk.IntVar(value=1000)
        self.safety_percent = tk.IntVar(value=25)  # % of input tokens as buffer

        # Processing mode and chunking
        self.processing_mode = tk.StringVar(value=PROCESSING_MODES[0])
        self.chunk_overlap_chars = tk.IntVar(value=800)

        # Data storage
        self.sections_db = []

        self.setup_ui()

    # ------------------ UI ------------------
    def setup_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # --- Server & Model Controls ---
        server = ttk.LabelFrame(main, text="Ollama & Model")
        server.grid(row=0, column=0, columnspan=6, sticky=(tk.W, tk.E), pady=6)

        ttk.Label(server, text="Server URL:").grid(row=0, column=0, padx=5)
        ent = ttk.Entry(server, textvariable=self.ollama_host, width=50)
        ent.grid(row=0, column=1, padx=5)
        ent.bind('<KeyRelease>', self._on_server_url_changed)
        ttk.Button(server, text="Refresh Models", command=self._refresh_models).grid(row=0, column=2, padx=5)

        ttk.Label(server, text="Model:").grid(row=1, column=0, padx=5)
        self.model_combo = ttk.Combobox(server, textvariable=self.selected_model, values=self.qwen_models, state="readonly", width=40)
        self.model_combo.grid(row=1, column=1, padx=5)

        # --- Processing Mode & Context ---
        mode = ttk.LabelFrame(main, text="Processing & Context")
        mode.grid(row=1, column=0, columnspan=6, sticky=(tk.W, tk.E), pady=6)

        ttk.Label(mode, text="Mode:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.mode_combo = ttk.Combobox(mode, textvariable=self.processing_mode, values=PROCESSING_MODES, state="readonly", width=15)
        self.mode_combo.grid(row=0, column=1, padx=5)

        ttk.Label(mode, text="Context Window (tokens):").grid(row=0, column=2, padx=5, sticky=tk.W)
        self.ctx_combo = ttk.Combobox(mode, values=[str(x) for x in CONTEXT_PRESETS], state="readonly", width=10)
        self.ctx_combo.set(str(self.context_tokens.get()))
        self.ctx_combo.grid(row=0, column=3, padx=5)
        self.ctx_combo.bind('<<ComboboxSelected>>', self._on_context_selected)

        ttk.Label(mode, text="Output Allowance (tokens):").grid(row=0, column=4, padx=5, sticky=tk.W)
        out_spin = ttk.Spinbox(mode, from_=500, to=20000, increment=500, textvariable=self.output_tokens, width=8, command=self._update_budget_status)
        out_spin.grid(row=0, column=5, padx=5)

        ttk.Label(mode, text="Prompt+Overhead (tokens):").grid(row=1, column=0, padx=5, sticky=tk.W)
        over_spin = ttk.Spinbox(mode, from_=0, to=10000, increment=250, textvariable=self.prompt_overhead_tokens, width=8, command=self._update_budget_status)
        over_spin.grid(row=1, column=1, padx=5)

        ttk.Label(mode, text="Safety Buffer (% of input)").grid(row=1, column=2, padx=5, sticky=tk.W)
        safety_spin = ttk.Spinbox(mode, from_=0, to=50, increment=5, textvariable=self.safety_percent, width=8, command=self._update_budget_status)
        safety_spin.grid(row=1, column=3, padx=5)

        # Chunking controls
        ttk.Label(mode, text="Chunk Overlap (chars):").grid(row=1, column=4, padx=5, sticky=tk.W)
        ov_spin = ttk.Spinbox(mode, from_=0, to=5000, increment=100, textvariable=self.chunk_overlap_chars, width=8)
        ov_spin.grid(row=1, column=5, padx=5)

        # Budget status
        self.budget_label = ttk.Label(mode, text="")
        self.budget_label.grid(row=2, column=0, columnspan=6, sticky=tk.W, padx=5)
        self._update_budget_status()

        # --- JSON Mode ---
        jframe = ttk.LabelFrame(main, text="Extraction Mode")
        jframe.grid(row=2, column=0, columnspan=6, sticky=(tk.W, tk.E), pady=6)
        ttk.Label(jframe, text="JSON Mode:").grid(row=0, column=0, padx=5)
        self.json_combo = ttk.Combobox(jframe, textvariable=self.json_mode, values=["structured", "simple", "prompt_only"], state="readonly", width=15)
        self.json_combo.grid(row=0, column=1, padx=5)
        self.json_combo.bind('<<ComboboxSelected>>', self._on_json_mode_changed)
        self.json_status = ttk.Label(jframe, text="Mode: Prompt Only", foreground="green")
        self.json_status.grid(row=0, column=2, padx=5)

        # --- Controls ---
        ctrl = ttk.Frame(main)
        ctrl.grid(row=3, column=0, columnspan=6, sticky=(tk.W, tk.E), pady=6)
        self.start_btn = ttk.Button(ctrl, text="Start", command=self.start_batch_processing)
        self.start_btn.grid(row=0, column=0, padx=5)
        self.pause_btn = ttk.Button(ctrl, text="Pause", command=self.pause_processing, state="disabled")
        self.pause_btn.grid(row=0, column=1, padx=5)
        self.stop_btn = ttk.Button(ctrl, text="Stop", command=self.stop_processing, state="disabled")
        self.stop_btn.grid(row=0, column=2, padx=5)
        ttk.Button(ctrl, text="Export Combined JSON", command=self.export_json).grid(row=0, column=3, padx=5)
        ttk.Button(ctrl, text="Save Progress", command=self.save_progress).grid(row=0, column=4, padx=5)

        # --- Progress & Status ---
        prog = ttk.Frame(main)
        prog.grid(row=4, column=0, columnspan=6, pady=6, sticky=(tk.W, tk.E))
        ttk.Label(prog, text="Progress:").grid(row=0, column=0)
        self.progress = ttk.Progressbar(prog, length=800, mode='indeterminate')
        self.progress.grid(row=0, column=1, padx=5, sticky=(tk.W, tk.E))
        self.progress_label = ttk.Label(prog, text="Idle")
        self.progress_label.grid(row=0, column=2)

        # --- Text Areas ---
        txt = ttk.Frame(main)
        txt.grid(row=5, column=0, columnspan=6, sticky=(tk.W, tk.E, tk.N, tk.S), pady=6)
        ttk.Label(txt, text="Source Text:").grid(row=0, column=0, sticky=tk.W)
        self.input_text = scrolledtext.ScrolledText(txt, height=22, width=90)
        self.input_text.grid(row=1, column=0, padx=5, sticky=(tk.W, tk.E, tk.N, tk.S))
        ttk.Label(txt, text="Model Output:").grid(row=0, column=1, sticky=tk.W)
        self.output_text = scrolledtext.ScrolledText(txt, height=22, width=90)
        self.output_text.grid(row=1, column=1, padx=5, sticky=(tk.W, tk.E, tk.N, tk.S))
        ttk.Label(txt, text="Log:").grid(row=0, column=2, sticky=tk.W)
        self.log_text = scrolledtext.ScrolledText(txt, height=22, width=60)
        self.log_text.grid(row=1, column=2, padx=5, sticky=(tk.W, tk.E, tk.N, tk.S))

        main.columnconfigure(0, weight=1)
        main.rowconfigure(5, weight=1)
        txt.columnconfigure(0, weight=1)
        txt.columnconfigure(1, weight=1)
        txt.columnconfigure(2, weight=1)
        txt.rowconfigure(1, weight=1)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(main, textvariable=self.status_var, relief=tk.SUNKEN).grid(row=6, column=0, columnspan=6, sticky=(tk.W, tk.E))

        # Auto refresh models
        if not self.qwen_models:
            self.start_btn.config(state="disabled")
        self._refresh_models()
        self._on_json_mode_changed()

    # ------------------ Helpers ------------------
    def _on_server_url_changed(self, event=None):
        try:
            new_host = self.ollama_host.get().strip()
            self.ollama_url = f"{new_host}/api/generate"
            if new_host.startswith('http') and len(new_host) > 10:
                self.log(f"Server URL updated to: {new_host}")
        except Exception:
            pass

    def _on_context_selected(self, event=None):
        try:
            self.context_tokens.set(int(self.ctx_combo.get()))
            self._update_budget_status()
        except Exception:
            pass

    def _update_budget_status(self):
        char_budget = self._compute_char_budget()
        msg = (
            f"Budget → input≈{self._available_input_tokens()} tokens (~{char_budget:,} chars) | "
            f"ctx={self.context_tokens.get():,} | output={self.output_tokens.get():,} | overhead={self.prompt_overhead_tokens.get():,} | safety={self.safety_percent.get()}%"
        )
        self.budget_label.config(text=msg)

    def _available_input_tokens(self):
        ctx = self.context_tokens.get()
        overhead = self.prompt_overhead_tokens.get() + self.output_tokens.get()
        safety = int(0.01 * self.safety_percent.get() * (ctx - overhead))
        return max(ctx - overhead - safety, 1000)

    def _compute_char_budget(self):
        return self._available_input_tokens() * CHARS_PER_TOKEN

    def _refresh_models(self):
        self.qwen_models = self._fetch_models()
        self.model_combo.config(values=self.qwen_models)
        if self.qwen_models:
            self.selected_model.set(self.qwen_models[0])
            self.start_btn.config(state="normal")
            self.log(f"Model list refreshed. Found {len(self.qwen_models)} models (sorted A–Z)")
        else:
            self.selected_model.set("")
            self.start_btn.config(state="disabled")
            self.log("Model list refreshed. No models found.")

    def _fetch_models(self):
        url = f"{self.ollama_host.get()}/api/tags"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                self.log(f"Failed to fetch models: HTTP {resp.status_code}")
                return []
            data = resp.json()
            if isinstance(data, dict) and 'models' in data:
                names = []
                for m in data['models']:
                    if isinstance(m, dict) and 'name' in m:
                        names.append(m['name'])
                    elif isinstance(m, str):
                        names.append(m)
                names.sort(key=str.lower)
                return names
            return []
        except Exception as e:
            self.log(f"Model fetch error: {e}")
            return []

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}\n"
        self.root.after(0, lambda: self.log_text.insert(tk.END, entry))
        self.root.after(0, lambda: self.log_text.see(tk.END))

    # ------------------ Run controls ------------------
    def start_batch_processing(self):
        if self.processing:
            return
        model = self.selected_model.get().strip()
        if not model:
            messagebox.showerror("No model", "No Ollama models were found. Click 'Refresh Models' or fix the server URL.")
            return
        self.processing = True
        self.paused = False
        self.ollama_url = f"{self.ollama_host.get()}/api/generate"
        self.progress_label.config(text="Running…")
        self.progress.start(10)
        self.start_btn.config(state="disabled")
        self.pause_btn.config(state="normal")
        self.stop_btn.config(state="normal")
        threading.Thread(target=self._run_batch, daemon=True).start()

    def pause_processing(self):
        if not self.processing:
            return
        self.paused = not self.paused
        self.pause_btn.config(text="Resume" if self.paused else "Pause")
        self.status_var.set("Paused" if self.paused else "Running")
        self.log("Processing paused." if self.paused else "Processing resumed.")

    def stop_processing(self):
        self.processing = False
        self.paused = False
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled", text="Pause")
        self.stop_btn.config(state="disabled")
        self.progress.stop()
        self.progress_label.config(text="Stopped")
        self.status_var.set("Stopped")
        self.log("Processing stopped by user.")

    # ------------------ Batch engine ------------------
    def _discover_pdfs(self):
        pdfs = []
        try:
            for name in os.listdir(self.base_dir):
                if name.lower().endswith('.pdf'):
                    pdfs.append(os.path.join(self.base_dir, name))
            pdfs.sort()
        except Exception as e:
            self.log(f"Directory read error: {e}")
        return pdfs

    def _run_batch(self):
        files = self._discover_pdfs()
        if not files:
            self.log(f"No PDFs found in: {self.base_dir}")
            self._complete()
            return

        mode = self.processing_mode.get()
        self.log(f"Mode: {mode} | Context tokens: {self.context_tokens.get():,}")
        char_budget = self._compute_char_budget()
        self.log(f"Estimated input char budget: ~{char_budget:,} chars")

        for fi, pdf_path in enumerate(files, start=1):
            if not self.processing:
                break
            while self.paused and self.processing:
                time.sleep(0.25)
            try:
                if mode == "Per Page":
                    self._process_pdf_per_page(pdf_path, fi)
                elif mode == "Whole File":
                    self._process_pdf_whole(pdf_path, fi, char_budget)
                else:  # Chunked
                    self._process_pdf_chunked(pdf_path, fi, char_budget)
            except Exception as e:
                self.log(f"Error processing {os.path.basename(pdf_path)}: {e}")
        self._complete()

    # ---------- Modes ----------
    def _process_pdf_per_page(self, pdf_path, file_index):
        reader = PyPDF2.PdfReader(pdf_path)
        total_pages = len(reader.pages)
        self.log(f"{os.path.basename(pdf_path)} — {total_pages} pages (Per Page)")
        prev_context = ""
        for p in range(total_pages):
            if not self.processing:
                break
            while self.paused and self.processing:
                time.sleep(0.25)
            text = reader.pages[p].extract_text() or ""
            self._display_source(text)
            context_prompt = self._make_context_prompt(prev_context) if prev_context else ""
            ok = self._process_with_qwen(
                unit_label=f"{os.path.basename(pdf_path)} — page {p+1}/{total_pages}",
                content=text,
                context_prompt=context_prompt,
                num_ctx=self.context_tokens.get(),
                source_file=pdf_path
            )
            if text:
                # Keep limited spillover context (chars) ~ 1/6 of char budget, capped 6k
                spill = min(len(text), max(1000, min(6000, self._compute_char_budget()//6)))
                prev_context = text[-spill:]
            self.log(f"Page {p+1}/{total_pages} {'✓' if ok else '✗'}")

    def _process_pdf_whole(self, pdf_path, file_index, char_budget):
        text = self._load_pdf_content(pdf_path) or ""
        self.log(f"{os.path.basename(pdf_path)} — length {len(text):,} chars (Whole File)")
        if len(text) > char_budget:
            self.log(f"⚠ File exceeds input budget (~{char_budget:,} chars). Sending truncated content.")
            text_to_send = text[:char_budget]
        else:
            text_to_send = text
        self._display_source(text_to_send)
        ok = self._process_with_qwen(
            unit_label=f"{os.path.basename(pdf_path)} — whole file",
            content=text_to_send,
            context_prompt="",
            num_ctx=self.context_tokens.get(),
            source_file=pdf_path
        )
        self.log(f"Whole file {'✓' if ok else '✗'}: {os.path.basename(pdf_path)}")

    def _process_pdf_chunked(self, pdf_path, file_index, char_budget):
        text = self._load_pdf_content(pdf_path) or ""
        overlap = max(0, int(self.chunk_overlap_chars.get()))
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + char_budget, len(text))
            chunks.append(text[start:end])
            if end == len(text):
                break
            start = end - overlap if end - overlap > start else end
        self.log(f"{os.path.basename(pdf_path)} — {len(chunks)} chunks @ ~{char_budget:,} chars, overlap {overlap} (Chunked)")
        for ci, chunk in enumerate(chunks, start=1):
            if not self.processing:
                break
            while self.paused and self.processing:
                time.sleep(0.25)
            self._display_source(chunk)
            ok = self._process_with_qwen(
                unit_label=f"{os.path.basename(pdf_path)} — chunk {ci}/{len(chunks)}",
                content=chunk,
                context_prompt="",
                num_ctx=self.context_tokens.get(),
                source_file=pdf_path
            )
            self.log(f"Chunk {ci}/{len(chunks)} {'✓' if ok else '✗'}")

    # ------------------ Core LLM call ------------------
    def _make_context_prompt(self, prev_text):
        if not prev_text:
            return ""
        limited = prev_text[-min(len(prev_text), 6000):]
        return f"""
CONTEXT FROM PREVIOUS UNIT (for spillover handling):
{limited}

--- CURRENT UNIT CONTENT ---
"""

    def _process_with_qwen(self, unit_label, content, context_prompt, num_ctx, source_file):
        self.root.after(0, lambda: self.output_text.delete(1.0, tk.END))

        # Build prompt depending on JSON mode
        json_mode = self.json_mode.get()
        if json_mode == "structured":
            prompt = f"""CRITICAL: Extract EACH Masterformat section number as a SEPARATE JSON section object.

{context_prompt}

🚨 RULES
1. EVERY "XX XX XX" or "XX XX XX.XX" = ONE separate section
2. Do NOT combine sections; attach labeled lists to the nearest preceding header only
3. Return ONLY JSON

TEXT TO PARSE:
{content}
"""
        else:
            prompt = f"""You are a Masterformat specification parser. Extract EACH section separately.

{context_prompt}

Rules:
- Treat each "XX XX XX" or "XX XX XX.XX" as a distinct section.
- Attach 'Includes', 'May Include', 'Products', 'Alternate Terms/Abbreviations', 'See', 'See Also' to the nearest preceding section header only.
- Return ONLY valid JSON, no commentary.

TEXT TO PARSE:
{content}
"""

        json_schema = {
            "type": "object",
            "properties": {
                "unit": {"type": "string"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "section_number": {"type": "string"},
                            "title": {"type": "string"},
                            "includes": {"type": "array", "items": {"type": "string"}},
                            "may_include": {"type": "array", "items": {"type": "string"}},
                            "products": {"type": "array", "items": {"type": "string"}},
                            "alternate_terms": {"type": "array", "items": {"type": "string"}},
                            "see": {"type": "array", "items": {"type": "object", "properties": {"section_number": {"type":"string"}, "description": {"type":"string"}}, "required": ["section_number", "description"]}},
                            "see_also": {"type": "array", "items": {"type": "object", "properties": {"section_number": {"type":"string"}, "description": {"type":"string"}}, "required": ["section_number", "description"]}},
                            "sub_sections": {"type": "array", "items": {"type": "object", "properties": {"section_number": {"type":"string"}, "title": {"type":"string"}}, "required": ["section_number", "title"]}},
                            "raw_text": {"type": "string"}
                        },
                        "required": ["section_number", "title"]
                    }
                }
            },
            "required": ["sections"],
            "additionalProperties": False
        }

        payload = {
            "model": self.selected_model.get(),
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.1,
                "num_predict": max(512, int(self.output_tokens.get())),
                "num_ctx": int(num_ctx)
            }
        }

        if json_mode == "structured":
            payload["format"] = json_schema
        elif json_mode == "simple":
            payload["format"] = "json"

        self.log(f"→ {unit_label} | ctx={num_ctx:,} predict={payload['options']['num_predict']:,}")

        try:
            resp = requests.post(self.ollama_url, json=payload, stream=True, timeout=180)
        except Exception as e:
            self.log(f"Network error: {e}")
            return False

        if resp.status_code != 200:
            self.log(f"HTTP {resp.status_code}: {resp.text[:200]}")
            return False

        full = ""
        for line in resp.iter_lines():
            if not self.processing:
                return False
            if not line:
                continue
            try:
                chunk = json.loads(line.decode('utf-8'))
                txt_chunk = chunk.get('response', '')
                full += txt_chunk
                self.root.after(0, lambda t=txt_chunk: self.output_text.insert(tk.END, t))
                self.root.after(0, lambda: self.output_text.see(tk.END))
                if chunk.get('done', False):
                    break
            except json.JSONDecodeError:
                continue

        # Save unit
        meta_label = unit_label
        ok = self._save_unit_data(meta_label, content, full, source_file)
        return ok

    def _display_source(self, text):
        self.root.after(0, lambda: self.input_text.delete(1.0, tk.END))
        self.root.after(0, lambda t=text: self.input_text.insert(1.0, t))

    # ------------------ Persistence ------------------
    def _load_pdf_content(self, path):
        try:
            reader = PyPDF2.PdfReader(path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            self.log(f"PDF load error: {e}")
            return None

    def _save_unit_data(self, unit_label, content, response_text, pdf_path):
        try:
            # Try to extract JSON body
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            structured_data = None
            if json_start != -1 and json_end > json_start:
                try:
                    structured_data = json.loads(response_text[json_start:json_end])
                except json.JSONDecodeError as e:
                    self.log(f"JSON parse warn ({unit_label}): {str(e)[:120]}…")

            page_data = {
                "metadata": {
                    "unit": unit_label,
                    "source_file": os.path.basename(pdf_path) if pdf_path else "",
                    "model": self.selected_model.get() or "unknown",
                    "timestamp": datetime.now().isoformat(),
                    "content_length": len(content or "")
                },
                "raw_content": content or "",
                "response_text": response_text or "",
                "structured": structured_data
            }

            # Save to file (safe write)
            safe_name = unit_label.replace(os.sep, "_").replace(' ', '_').replace('/', '_')
            out_path = os.path.join(self.output_dir, f"{safe_name[:150]}.json")
            os.makedirs(self.output_dir, exist_ok=True)
            tmp = f"{out_path}.tmp"
            with open(tmp, 'w', encoding='utf-8', errors='replace') as f:
                json.dump(page_data, f, indent=2, ensure_ascii=True)
                f.flush(); os.fsync(f.fileno())
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except Exception:
                    pass
            os.rename(tmp, out_path)

            self.sections_db.append(page_data)
            self.status_var.set(f"Saved: {os.path.basename(out_path)}")
            self.log(f"✓ Saved {os.path.basename(out_path)}")
            return True
        except Exception as e:
            self.log(f"Save error ({unit_label}): {e}")
            return False

    def save_progress(self):
        if not self.sections_db:
            messagebox.showwarning("Warning", "No data to save")
            return
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"masterformat_progress_{ts}.json"
        path = os.path.join(self.base_dir, filename)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.sections_db, f, indent=2, ensure_ascii=True)
            self.log(f"✓ Progress saved: {filename}")
            messagebox.showinfo("Saved", f"Progress saved to {filename}")
        except Exception as e:
            self.log(f"Progress save error: {e}")
            messagebox.showerror("Error", str(e))

    def export_json(self):
        if not self.sections_db:
            messagebox.showwarning("Warning", "No data to export")
            return
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_filename = f"masterformat_combined_{ts}.json"
        save_path = filedialog.asksaveasfilename(title="Export Combined JSON", defaultextension=".json", filetypes=[("JSON","*.json")], initialdir=self.base_dir, initialfile=default_filename)
        if not save_path:
            return
        try:
            export_data = {
                "export_info": {
                    "export_timestamp": datetime.now().isoformat(),
                    "units": len(self.sections_db),
                    "model_used": self.selected_model.get(),
                    "ctx_tokens": self.context_tokens.get(),
                },
                "data": self.sections_db
            }
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=True)
            self.log(f"✓ Exported: {os.path.basename(save_path)}")
            messagebox.showinfo("Exported", os.path.basename(save_path))
        except Exception as e:
            self.log(f"Export error: {e}")
            messagebox.showerror("Error", str(e))

    def _on_json_mode_changed(self, event=None):
        try:
            mode = self.json_mode.get()
            status_map = {
                "structured": "Mode: Structured (schema)",
                "simple": "Mode: Simple JSON",
                "prompt_only": "Mode: Prompt Only"
            }
            self.json_status.config(text=status_map.get(mode, "Mode: Unknown"))
            self.log(f"JSON mode: {mode}")
        except Exception:
            pass

    def _complete(self):
        self.processing = False
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled")
        self.stop_btn.config(state="disabled")
        self.progress.stop()
        self.progress_label.config(text="Idle")
        self.status_var.set("Complete")
        self.log("Batch processing complete.")

# ------------------ main ------------------

def main():
    root = tk.Tk()
    app = MasterformatProcessor(root)
    root.mainloop()

if __name__ == "__main__":
    main()
