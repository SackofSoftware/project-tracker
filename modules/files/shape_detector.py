"""
Shape Detector for Construction Drawing Tags

Detects standard tag shapes (hexagons, circles, rectangles, etc.) in PDF pages
and extracts the text labels inside them.
"""

import fitz
import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class ShapeType(Enum):
    HEXAGON = "hexagon"
    CIRCLE = "circle"
    RECTANGLE = "rectangle"
    DIAMOND = "diamond"
    TRIANGLE = "triangle"


@dataclass
class DetectedTag:
    """A detected tag shape with its label"""
    shape_type: ShapeType
    label: str
    pdf_x: float
    pdf_y: float
    width: float
    height: float
    confidence: float

    def to_dict(self) -> dict:
        return {
            'shape_type': self.shape_type.value,
            'label': self.label,
            'pdf_x': self.pdf_x,
            'pdf_y': self.pdf_y,
            'width': self.width,
            'height': self.height,
            'confidence': self.confidence
        }


class ShapeDetector:
    """Detects tag shapes in PDF pages"""

    # Shape detection parameters
    SHAPE_PARAMS = {
        ShapeType.HEXAGON: {
            'vertices': 6,
            'min_area': 200,
            'max_area': 8000,
            'aspect_range': (0.7, 1.4),
            'epsilon_factor': 0.03
        },
        ShapeType.CIRCLE: {
            'vertices': (8, 20),  # Range for circle approximation
            'min_area': 200,
            'max_area': 8000,
            'circularity_min': 0.7,
            'epsilon_factor': 0.02
        },
        ShapeType.RECTANGLE: {
            'vertices': 4,
            'min_area': 200,
            'max_area': 10000,
            'aspect_range': (0.3, 3.0),
            'epsilon_factor': 0.02
        },
        ShapeType.DIAMOND: {
            'vertices': 4,
            'min_area': 200,
            'max_area': 8000,
            'rotation_check': True,  # Check if rotated 45 degrees
            'epsilon_factor': 0.03
        },
        ShapeType.TRIANGLE: {
            'vertices': 3,
            'min_area': 150,
            'max_area': 5000,
            'epsilon_factor': 0.03
        }
    }

    def __init__(self, render_scale: float = 2.0):
        """
        Initialize detector.

        Args:
            render_scale: Scale factor for PDF rendering (higher = more accurate but slower)
        """
        self.render_scale = render_scale

    def detect_shapes(
        self,
        pdf_path: str,
        page_num: int,
        shape_type: ShapeType,
        min_confidence: float = 0.5
    ) -> List[DetectedTag]:
        """
        Detect all shapes of specified type on a PDF page.

        Args:
            pdf_path: Path to PDF file
            page_num: Page number (1-indexed)
            shape_type: Type of shape to detect
            min_confidence: Minimum confidence threshold

        Returns:
            List of detected tags
        """
        doc = fitz.open(pdf_path)
        page = doc[page_num - 1]  # Convert to 0-indexed

        # Get page dimensions
        page_rect = page.rect

        # Render page to image
        mat = fitz.Matrix(self.render_scale, self.render_scale)
        pix = page.get_pixmap(matrix=mat)

        # Convert to numpy array
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )

        # Convert to grayscale
        if pix.n == 4:
            gray = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
        else:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # Get text positions from PDF (more accurate than OCR)
        text_blocks = self._get_text_positions(page)

        # Threshold for binary image
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

        # Find contours
        contours, hierarchy = cv2.findContours(
            binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )

        # Detect shapes
        detected = []
        params = self.SHAPE_PARAMS[shape_type]

        for cnt in contours:
            result = self._check_shape(cnt, shape_type, params)
            if result is None:
                continue

            x, y, w, h, confidence = result

            if confidence < min_confidence:
                continue

            # Convert pixel coordinates to PDF coordinates
            pdf_x = x / self.render_scale
            pdf_y = y / self.render_scale
            pdf_w = w / self.render_scale
            pdf_h = h / self.render_scale

            # Find text label inside this shape
            label = self._find_label_at(
                text_blocks,
                pdf_x, pdf_y, pdf_w, pdf_h
            )

            detected.append(DetectedTag(
                shape_type=shape_type,
                label=label,
                pdf_x=pdf_x,
                pdf_y=pdf_y,
                width=pdf_w,
                height=pdf_h,
                confidence=confidence
            ))

        doc.close()

        # Remove duplicates (shapes detected multiple times)
        detected = self._remove_duplicates(detected)

        # Sort by position (top to bottom, left to right)
        detected.sort(key=lambda t: (t.pdf_y, t.pdf_x))

        return detected

    def _check_shape(
        self,
        contour,
        shape_type: ShapeType,
        params: dict
    ) -> Optional[Tuple[int, int, int, int, float]]:
        """
        Check if contour matches the specified shape type.

        Returns (x, y, w, h, confidence) if match, None otherwise.
        """
        area = cv2.contourArea(contour)

        # Check area bounds
        if area < params['min_area'] or area > params['max_area']:
            return None

        # Approximate polygon
        epsilon = params['epsilon_factor'] * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        vertices = len(approx)

        x, y, w, h = cv2.boundingRect(contour)
        aspect = w / h if h > 0 else 0

        confidence = 0.0

        if shape_type == ShapeType.HEXAGON:
            if vertices != 6:
                return None
            if not (params['aspect_range'][0] < aspect < params['aspect_range'][1]):
                return None
            # Confidence based on regularity
            confidence = self._hexagon_regularity(approx)

        elif shape_type == ShapeType.CIRCLE:
            min_v, max_v = params['vertices']
            if not (min_v <= vertices <= max_v):
                return None
            # Check circularity
            perimeter = cv2.arcLength(contour, True)
            circularity = 4 * np.pi * area / (perimeter * perimeter) if perimeter > 0 else 0
            if circularity < params['circularity_min']:
                return None
            confidence = circularity

        elif shape_type == ShapeType.RECTANGLE:
            if vertices != 4:
                return None
            if not (params['aspect_range'][0] < aspect < params['aspect_range'][1]):
                return None
            # Check if angles are roughly 90 degrees
            confidence = self._rectangle_confidence(approx)

        elif shape_type == ShapeType.DIAMOND:
            if vertices != 4:
                return None
            # Check if it's rotated (diamond shape)
            confidence = self._diamond_confidence(approx, w, h)
            if confidence < 0.5:
                return None

        elif shape_type == ShapeType.TRIANGLE:
            if vertices != 3:
                return None
            confidence = 0.8  # Triangles are straightforward

        return (x, y, w, h, confidence)

    def _hexagon_regularity(self, approx) -> float:
        """Calculate how regular a hexagon is (0-1)"""
        if len(approx) != 6:
            return 0.0

        # Calculate side lengths
        points = approx.reshape(-1, 2)
        sides = []
        for i in range(6):
            p1 = points[i]
            p2 = points[(i + 1) % 6]
            sides.append(np.linalg.norm(p2 - p1))

        # Regular hexagon has equal sides
        mean_side = np.mean(sides)
        if mean_side == 0:
            return 0.0

        variance = np.std(sides) / mean_side
        regularity = max(0, 1 - variance)

        return regularity

    def _rectangle_confidence(self, approx) -> float:
        """Calculate confidence that shape is a rectangle"""
        if len(approx) != 4:
            return 0.0

        points = approx.reshape(-1, 2)

        # Check angles (should be ~90 degrees)
        angles = []
        for i in range(4):
            p1 = points[(i - 1) % 4]
            p2 = points[i]
            p3 = points[(i + 1) % 4]

            v1 = p1 - p2
            v2 = p3 - p2

            cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
            angle = np.arccos(np.clip(cos_angle, -1, 1))
            angles.append(abs(angle - np.pi/2))

        # Average deviation from 90 degrees
        avg_deviation = np.mean(angles)
        confidence = max(0, 1 - avg_deviation / (np.pi/4))

        return confidence

    def _diamond_confidence(self, approx, w, h) -> float:
        """Calculate confidence that shape is a diamond (rotated square)"""
        if len(approx) != 4:
            return 0.0

        points = approx.reshape(-1, 2)

        # Diamond has vertices at top, bottom, left, right
        # Check if the extreme points are at the midpoints of edges
        cx, cy = np.mean(points, axis=0)

        # Find points closest to top, bottom, left, right
        top_idx = np.argmin(points[:, 1])
        bottom_idx = np.argmax(points[:, 1])
        left_idx = np.argmin(points[:, 0])
        right_idx = np.argmax(points[:, 0])

        # Check if these are 4 different points
        if len(set([top_idx, bottom_idx, left_idx, right_idx])) != 4:
            return 0.0

        # Check aspect ratio is roughly square
        aspect = w / h if h > 0 else 0
        if not (0.7 < aspect < 1.4):
            return 0.0

        return 0.8

    def _get_text_positions(self, page) -> List[dict]:
        """Extract text positions from PDF page"""
        text_blocks = []

        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            if block.get("type") == 0:  # Text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if text:
                            bbox = span.get("bbox", (0, 0, 0, 0))
                            text_blocks.append({
                                'text': text,
                                'x': bbox[0],
                                'y': bbox[1],
                                'x2': bbox[2],
                                'y2': bbox[3],
                                'cx': (bbox[0] + bbox[2]) / 2,
                                'cy': (bbox[1] + bbox[3]) / 2
                            })

        return text_blocks

    def _find_label_at(
        self,
        text_blocks: List[dict],
        x: float, y: float, w: float, h: float
    ) -> str:
        """Find text label inside or near the specified bounding box"""
        cx = x + w / 2
        cy = y + h / 2

        # Look for text whose center is inside the shape
        best_match = None
        best_dist = float('inf')

        # Use a larger search radius for small shapes
        search_radius = max(w, h) * 1.5

        for tb in text_blocks:
            # Distance from shape center to text center
            dist = ((tb['cx'] - cx) ** 2 + (tb['cy'] - cy) ** 2) ** 0.5

            if dist < search_radius and dist < best_dist:
                # Prefer shorter text (single letters/short codes are more likely to be labels)
                text = tb['text'].strip()
                if len(text) <= 6:  # Short labels only
                    best_dist = dist
                    best_match = text

        return best_match or ""

    def _remove_duplicates(
        self,
        tags: List[DetectedTag],
        threshold: float = 10.0
    ) -> List[DetectedTag]:
        """Remove duplicate detections that are too close together"""
        if not tags:
            return []

        unique = []
        for tag in tags:
            is_duplicate = False
            for existing in unique:
                dist = ((tag.pdf_x - existing.pdf_x) ** 2 +
                       (tag.pdf_y - existing.pdf_y) ** 2) ** 0.5
                if dist < threshold:
                    # Keep the one with higher confidence
                    if tag.confidence > existing.confidence:
                        unique.remove(existing)
                        unique.append(tag)
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique.append(tag)

        return unique


def detect_tags_on_page(
    pdf_path: str,
    page_num: int,
    shape_type: str = "hexagon",
    min_confidence: float = 0.5
) -> List[dict]:
    """
    Convenience function to detect tags on a PDF page.

    Args:
        pdf_path: Path to PDF file
        page_num: Page number (1-indexed)
        shape_type: One of: hexagon, circle, rectangle, diamond, triangle
        min_confidence: Minimum confidence threshold (0-1)

    Returns:
        List of detected tags as dictionaries
    """
    detector = ShapeDetector()
    shape_enum = ShapeType(shape_type)

    tags = detector.detect_shapes(pdf_path, page_num, shape_enum, min_confidence)

    return [tag.to_dict() for tag in tags]
