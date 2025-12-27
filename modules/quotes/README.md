# Quote Reader Module

AI-powered vendor quote analysis for Division 8 project tracking.

## Overview

The Quote Reader module automatically finds and analyzes vendor quote PDFs in project folders, extracting pricing data and comparing it with internal estimates.

## Features

- **Automatic Quote Detection**: Finds quote PDFs based on filename patterns and vendor names
- **AI-Powered Extraction**: Uses OpenRouter AI (Amazon Nova Lite) to extract structured data from PDFs
- **Quote Comparison**: Side-by-side comparison table with color-coded pricing
- **Multi-Vendor Support**: Handles multiple quotes from different vendors
- **Integration with Estimates**: Automatically compares vendor quotes against internal estimates

## File Patterns

The module searches for PDFs matching these patterns:
- `*quote*.pdf`
- `*pricing*.pdf`
- `*proposal*.pdf`
- `*estimate*.pdf`
- `*bid*.pdf`

It also recognizes common vendor names:
- kawneer, oldcastle, tubelite, ykk, hope
- doormerica, graham, allegion, assa, stanley
- crl, viracon, ppg, guardian

## Folder Structure

Quotes are automatically found in:
1. `{project_folder}/Quotes/` - dedicated quotes subfolder (checked first)
2. Root project folder and all subfolders

## Extracted Data

For each quote PDF, the AI extracts:
- Vendor name
- Quote number and date
- Contact information (rep, email, phone)
- Line items with:
  - Mark/tag (door/window reference)
  - Description
  - Quantity
  - Unit price
  - Total price
- Grand total
- Terms (payment, lead time)
- Special notes

## API Endpoint

### GET `/api/quotes/<project_id>`

Returns all vendor quotes found in the project folder.

**Response:**
```json
{
  "status": "ok",
  "quotes": [
    {
      "vendor_name": "ABC Windows Inc",
      "quote_number": "Q-12345",
      "quote_date": "2024-12-01",
      "line_items": [
        {
          "mark": "W-1",
          "description": "Fixed aluminum window",
          "qty": 10,
          "unit_price": 450,
          "total_price": 4500
        }
      ],
      "grand_total": 25000,
      "terms": "NET 30",
      "lead_time": "6-8 weeks",
      "source_file": "ABC_Quote_12345.pdf"
    }
  ],
  "total_quotes": 1,
  "vendors": ["ABC Windows Inc"],
  "total_value": 25000
}
```

## Usage

### Python API

```python
from modules.quotes import QuoteReader

# Create reader for a project
reader = QuoteReader('/path/to/project/folder')

# Read all quotes
result = reader.read_all_quotes()

# Access quote data
for quote in result['quotes']:
    print(f"{quote['vendor_name']}: ${quote['grand_total']}")
    for item in quote['line_items']:
        print(f"  {item['mark']}: ${item['total_price']}")
```

### UI

1. Navigate to a project detail page
2. Scroll to the "Vendor Quotes" section
3. Click "Load Quotes" button
4. View side-by-side comparison table with:
   - Green = vendor price lower than estimate
   - Red = vendor price higher than estimate
   - Yellow column = internal estimate

## AI Model

- **Provider**: OpenRouter
- **Model**: amazon/nova-lite-v1 (free tier)
- **API Key**: Set via `OPENROUTER_API_KEY` environment variable
- **Limits**: 10 requests/minute, 1000 requests/day

## Error Handling

The module gracefully handles:
- Missing or invalid PDFs
- PDFs with no extractable text
- AI API failures (falls back to basic file listing)
- Missing estimate data (shows quotes only)

## Performance

- PDF parsing: ~2-3 seconds per PDF
- AI extraction: ~3-5 seconds per PDF
- Concurrent processing: Quotes and estimates loaded in parallel
- Caching: Results cached in browser session

## Configuration

No configuration required. The module:
- Uses environment variable `OPENROUTER_API_KEY` for API access
- Falls back to non-AI mode if API key is missing
- Automatically finds quotes in standard locations

## Testing

```bash
# Test module import
python3 -c "from modules.quotes import QuoteReader; print('OK')"

# Test with a project folder
python3 modules/quotes/quote_reader.py
```

## Future Enhancements

- [ ] Support for Excel quote spreadsheets
- [ ] Quote version tracking
- [ ] Vendor performance scoring
- [ ] Automated quote request generation
- [ ] Quote expiration alerts
