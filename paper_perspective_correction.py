from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Sequence

import cv2
import numpy as np


A4_ASPECT_RATIO = 297 / 210


class PerspectiveCorrectionError(ValueError):
    pass


def parse_points(points: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float32)
    if pts.shape != (4, 2):
        raise PerspectiveCorrectionError(
            f"Expected 4 corner points with shape (4, 2), got {pts.shape}."
        )
    return pts


def order_points(points: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
    pts = parse_points(points)
    center = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    clockwise = pts[np.argsort(angles)]

    top_left_index = np.argmin(clockwise.sum(axis=1))
    clockwise = np.roll(clockwise, -top_left_index, axis=0)

    tl, p1, p2, p3 = clockwise
    cross_z = (p1[0] - tl[0]) * (p2[1] - p1[1]) - (p1[1] - tl[1]) * (p2[0] - p1[0])
    if cross_z < 0:
        clockwise = np.array([tl, p3, p2, p1], dtype=np.float32)

    return clockwise.astype(np.float32)


def _edge_lengths(rect: np.ndarray) -> tuple[float, float, float, float]:
    tl, tr, br, bl = rect
    width_top = float(np.linalg.norm(tr - tl))
    width_bottom = float(np.linalg.norm(br - bl))
    height_right = float(np.linalg.norm(br - tr))
    height_left = float(np.linalg.norm(bl - tl))
    return width_top, width_bottom, height_right, height_left


def compute_output_size(
    rect: np.ndarray,
    aspect_ratio: float | None = None,
    output_width: int | None = None,
    output_height: int | None = None,
) -> tuple[int, int]:
    width_top, width_bottom, height_right, height_left = _edge_lengths(rect)
    estimated_width = max(int(round(max(width_top, width_bottom))), 1)
    estimated_height = max(int(round(max(height_right, height_left))), 1)

    if output_width and output_height:
        return output_width, output_height

    if aspect_ratio is not None:
        if output_width:
            return output_width, max(int(round(output_width * aspect_ratio)), 1)
        if output_height:
            return max(int(round(output_height / aspect_ratio)), 1), output_height

        width_from_height = int(round(estimated_height / aspect_ratio))
        height_from_width = int(round(estimated_width * aspect_ratio))

        width_error = abs(width_from_height - estimated_width)
        height_error = abs(height_from_width - estimated_height)

        if width_error <= height_error:
            return max(width_from_height, 1), estimated_height
        return estimated_width, max(height_from_width, 1)

    if output_width:
        scale = output_width / estimated_width
        return output_width, max(int(round(estimated_height * scale)), 1)

    if output_height:
        scale = output_height / estimated_height
        return max(int(round(estimated_width * scale)), 1), output_height

    return estimated_width, estimated_height


def get_destination_points(width: int, height: int) -> np.ndarray:
    return np.array(
        [
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1],
        ],
        dtype=np.float32,
    )


def _resize_for_detection(image: np.ndarray, max_side: int = 1600) -> tuple[np.ndarray, float]:
    height, width = image.shape[:2]
    longest_side = max(height, width)
    if longest_side <= max_side:
        return image.copy(), 1.0

    scale = max_side / longest_side
    resized = cv2.resize(
        image,
        (int(round(width * scale)), int(round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def _normalize_mask(mask: np.ndarray) -> np.ndarray:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    normalized = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    normalized = cv2.morphologyEx(normalized, cv2.MORPH_OPEN, kernel, iterations=1)
    return normalized


def _build_detection_masks(image: np.ndarray) -> list[tuple[str, np.ndarray]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    _, light_mask = cv2.threshold(value, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, low_saturation = cv2.threshold(
        saturation, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    paper_mask = cv2.bitwise_and(light_mask, low_saturation)

    _, gray_otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        35,
        7,
    )
    adaptive_inv = cv2.bitwise_not(adaptive)
    edges = cv2.Canny(blurred, 40, 120)
    edge_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.dilate(edges, edge_kernel, iterations=2)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, edge_kernel, iterations=2)

    masks = [
        ("paper_mask", _normalize_mask(paper_mask)),
        ("gray_otsu", _normalize_mask(gray_otsu)),
        ("adaptive_inv", _normalize_mask(adaptive_inv)),
        ("edges", edges),
    ]
    return masks


def _contour_to_quad(contour: np.ndarray) -> np.ndarray | None:
    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 0:
        return None

    for epsilon_factor in (0.01, 0.02, 0.03, 0.05):
        polygon = cv2.approxPolyDP(contour, epsilon_factor * perimeter, True)
        if len(polygon) == 4 and cv2.isContourConvex(polygon):
            return polygon.reshape(4, 2).astype(np.float32)

    hull = cv2.convexHull(contour)
    if len(hull) < 4:
        return None

    rect = cv2.minAreaRect(hull)
    return cv2.boxPoints(rect).astype(np.float32)


def _score_quad(
    quad: np.ndarray,
    gray: np.ndarray,
    image_shape: tuple[int, int],
    expected_ratio: float,
) -> float:
    rect = order_points(quad)
    height, width = image_shape
    area = cv2.contourArea(rect)
    if area <= 0:
        return float("-inf")

    image_area = float(width * height)
    area_ratio = area / image_area
    if area_ratio > 0.92:
        return float("-inf")

    border_margin = 0.015 * min(width, height)
    near_left = rect[:, 0] <= border_margin
    near_right = rect[:, 0] >= width - 1 - border_margin
    near_top = rect[:, 1] <= border_margin
    near_bottom = rect[:, 1] >= height - 1 - border_margin
    border_hits = int(np.count_nonzero(near_left | near_right | near_top | near_bottom))
    touched_sides = sum(
        bool(flag.any()) for flag in (near_left, near_right, near_top, near_bottom)
    )
    if border_hits >= 2 or touched_sides >= 2:
        return float("-inf")

    width_top, width_bottom, height_right, height_left = _edge_lengths(rect)
    quad_width = max(width_top, width_bottom)
    quad_height = max(height_right, height_left)
    if quad_width < 1 or quad_height < 1:
        return float("-inf")

    aspect = max(quad_height / quad_width, quad_width / quad_height)
    aspect_score = max(0.0, 1.0 - abs(aspect - expected_ratio) / expected_ratio)

    fill_mask = np.zeros(gray.shape, dtype=np.uint8)
    cv2.fillConvexPoly(fill_mask, rect.astype(np.int32), 255)
    brightness_score = cv2.mean(gray, mask=fill_mask)[0] / 255.0

    center = rect.mean(axis=0)
    image_center = np.array([width / 2.0, height / 2.0], dtype=np.float32)
    diagonal = float(np.hypot(width, height))
    center_distance = float(np.linalg.norm(center - image_center) / diagonal)
    center_score = max(0.0, 1.0 - center_distance)

    return area_ratio * 2.5 + aspect_score * 1.8 + brightness_score * 0.8 + center_score * 0.6


def auto_detect_paper_corners(
    image: np.ndarray,
    *,
    expected_ratio: float = A4_ASPECT_RATIO,
    min_area_ratio: float = 0.08,
    max_side: int = 1600,
) -> tuple[np.ndarray, np.ndarray, str]:
    if image is None or image.size == 0:
        raise PerspectiveCorrectionError("Input image is empty.")

    resized, scale = _resize_for_detection(image, max_side=max_side)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    image_area = resized.shape[0] * resized.shape[1]
    min_area = image_area * min_area_ratio

    best_quad: np.ndarray | None = None
    best_mask: np.ndarray | None = None
    best_mask_name = ""
    best_score = float("-inf")

    for mask_name, mask in _build_detection_masks(resized):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            contour_area = cv2.contourArea(contour)
            if contour_area < min_area:
                continue

            quad = _contour_to_quad(contour)
            if quad is None:
                continue

            score = _score_quad(quad, gray, gray.shape, expected_ratio)
            if score > best_score:
                best_score = score
                best_quad = quad
                best_mask = mask
                best_mask_name = mask_name

    if best_quad is None or best_mask is None:
        raise PerspectiveCorrectionError("Automatic paper corner detection failed.")

    detected = order_points(best_quad / scale)
    return detected, best_mask, best_mask_name


def correct_paper_perspective(
    image: np.ndarray,
    points: Sequence[Sequence[float]] | np.ndarray,
    *,
    aspect_ratio: float | None = None,
    output_width: int | None = None,
    output_height: int | None = None,
    interpolation: int = cv2.INTER_CUBIC,
    border_mode: int = cv2.BORDER_REPLICATE,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if image is None or image.size == 0:
        raise PerspectiveCorrectionError("Input image is empty.")

    rect = order_points(points)
    width, height = compute_output_size(
        rect,
        aspect_ratio=aspect_ratio,
        output_width=output_width,
        output_height=output_height,
    )

    destination = get_destination_points(width, height)
    matrix = cv2.getPerspectiveTransform(rect, destination)
    corrected = cv2.warpPerspective(
        image,
        matrix,
        (width, height),
        flags=interpolation,
        borderMode=border_mode,
    )
    return corrected, matrix, rect


def auto_correct_paper_perspective(
    image: np.ndarray,
    *,
    aspect_ratio: float | None = None,
    output_width: int | None = None,
    output_height: int | None = None,
    expected_ratio: float = A4_ASPECT_RATIO,
    min_area_ratio: float = 0.08,
    max_side: int = 1600,
    interpolation: int = cv2.INTER_CUBIC,
    border_mode: int = cv2.BORDER_REPLICATE,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, str]:
    detected_points, debug_mask, mask_name = auto_detect_paper_corners(
        image,
        expected_ratio=expected_ratio,
        min_area_ratio=min_area_ratio,
        max_side=max_side,
    )
    corrected, matrix, ordered_points = correct_paper_perspective(
        image,
        detected_points,
        aspect_ratio=aspect_ratio,
        output_width=output_width,
        output_height=output_height,
        interpolation=interpolation,
        border_mode=border_mode,
    )
    return corrected, matrix, ordered_points, debug_mask, mask_name


def draw_corners(image: np.ndarray, points: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
    output = image.copy()
    rect = order_points(points)
    labels = ["TL", "TR", "BR", "BL"]
    polygon = rect.astype(np.int32).reshape((-1, 1, 2))
    cv2.polylines(output, [polygon], True, (0, 255, 255), 4, cv2.LINE_AA)
    for label, (x, y) in zip(labels, rect):
        center = (int(round(float(x))), int(round(float(y))))
        cv2.circle(output, center, 10, (0, 255, 0), -1)
        cv2.putText(
            output,
            label,
            (center[0] + 12, center[1] - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
    return output


def parse_points_string(value: str) -> np.ndarray:
    parts = [chunk.strip() for chunk in value.replace(";", " ").split() if chunk.strip()]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "Points must contain exactly four 'x,y' pairs, separated by spaces or semicolons."
        )

    parsed: list[list[float]] = []
    for part in parts:
        try:
            x_str, y_str = part.split(",", 1)
            parsed.append([float(x_str), float(y_str)])
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"Invalid point '{part}'. Expected format 'x,y'."
            ) from exc
    return np.asarray(parsed, dtype=np.float32)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Correct a paper image with four corner points or automatic corner detection."
    )
    parser.add_argument("--input", required=True, help="Path to the input image.")
    parser.add_argument("--output", required=True, help="Path to the corrected output image.")
    parser.add_argument(
        "--points",
        type=parse_points_string,
        default=None,
        help="Optional four 'x,y' pairs. Example: '120,80 980,95 1015,1420 90,1400'",
    )
    parser.add_argument(
        "--aspect-ratio",
        type=float,
        default=None,
        help="Optional height/width ratio for the output image.",
    )
    parser.add_argument(
        "--a4",
        action="store_true",
        help="Force A4 output ratio (height/width = 297/210).",
    )
    parser.add_argument("--width", type=int, default=None, help="Optional output width.")
    parser.add_argument("--height", type=int, default=None, help="Optional output height.")
    parser.add_argument(
        "--min-area-ratio",
        type=float,
        default=0.08,
        help="Minimum area ratio for automatic paper detection.",
    )
    parser.add_argument(
        "--debug-corners",
        default=None,
        help="Optional path to save the input image with ordered corner labels drawn on it.",
    )
    parser.add_argument(
        "--debug-mask",
        default=None,
        help="Optional path to save the binary mask used by automatic paper detection.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    image = cv2.imread(args.input)
    if image is None:
        raise SystemExit(f"Failed to read input image: {args.input}")

    aspect_ratio = A4_ASPECT_RATIO if args.a4 else args.aspect_ratio

    if args.points is None:
        corrected, matrix, ordered_points, debug_mask, mask_name = auto_correct_paper_perspective(
            image,
            aspect_ratio=aspect_ratio,
            output_width=args.width,
            output_height=args.height,
            expected_ratio=A4_ASPECT_RATIO,
            min_area_ratio=args.min_area_ratio,
        )
        detection_mode = f"auto:{mask_name}"
    else:
        corrected, matrix, ordered_points = correct_paper_perspective(
            image,
            args.points,
            aspect_ratio=aspect_ratio,
            output_width=args.width,
            output_height=args.height,
        )
        debug_mask = None
        detection_mode = "manual"

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    success = cv2.imwrite(str(output_path), corrected)
    if not success:
        raise SystemExit(f"Failed to write output image: {args.output}")

    if args.debug_corners:
        debug_image = draw_corners(image, ordered_points)
        debug_path = Path(args.debug_corners)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_path), debug_image)

    if args.debug_mask and debug_mask is not None:
        debug_mask_path = Path(args.debug_mask)
        debug_mask_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_mask_path), debug_mask)

    print(f"detection_mode={detection_mode}")
    print("ordered_points=", ordered_points.tolist())
    print("transform_matrix=")
    print(matrix)
    print(f"saved={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
