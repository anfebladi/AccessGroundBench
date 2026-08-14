import { useEffect, useRef, useState } from "react";
import { imageIsDrawable, strokeWidthFor } from "../../lib/canvas";
import { imageUrl } from "../../lib/api";
import type { Box, Label, Target } from "./types";
import { asText } from "./types";

export function ScreenshotCanvas({
  dataset, screen, profile, targets, present, missing, labels, selected,
  showBoxes, showMissing, evictedOnly, onSelect, id, wrapperRef,
  hidden, className, style, onDimensions, onCanvasReady,
}: {
  dataset: string; screen: string; profile: string; targets: Target[];
  present: Set<string>; missing: Target[]; labels: Label[]; selected: string | null;
  showBoxes: boolean; showMissing: boolean; evictedOnly: boolean;
  onSelect: (text: string) => void; id: string; wrapperRef: React.RefObject<HTMLDivElement | null>;
  hidden?: boolean; className?: string; style?: React.CSSProperties; onDimensions?: (value: string) => void;
  onCanvasReady?: (canvas: HTMLCanvasElement) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  useEffect(() => {
    const image = new Image();
    image.onload = () => setImg(image);
    image.onerror = () => setImg(image);
    image.src = imageUrl(dataset, screen, profile);
    return () => { image.onload = null; image.onerror = null; };
  }, [dataset, screen, profile]);
  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapperRef.current;
    if (!canvas || !img) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    if (!imageIsDrawable(img)) {
      canvas.width = 400;
      canvas.height = 80;
      ctx.clearRect(0, 0, 400, 80);
      ctx.fillStyle = "#b3221a";
      ctx.font = "14px sans-serif";
      ctx.fillText("Screenshot not available", 12, 44);
      onDimensions?.("—"); return;
    }
    canvas.width = img.width;
    canvas.height = img.height;
    ctx.drawImage(img, 0, 0);
    onDimensions?.(`${img.width} x ${img.height}`);
    if (!showBoxes) return;
    const sw = strokeWidthFor(img);
    const accent = "#2a78d6";
    const err = "#b3221a";
    const warn = "#a15c00";
    const draw = (text: string | undefined, b: Box | undefined, color: string) => {
      if (!b) return;
      const isSelected = text === selected;
      ctx.strokeStyle = isSelected ? warn : color;
      ctx.lineWidth = isSelected ? sw * 2.4 : sw;
      ctx.strokeRect(b[0], b[1], b[2] - b[0], b[3] - b[1]);
      if (isSelected && text) {
        ctx.font = `${Math.max(12, sw * 5)}px sans-serif`;
        const pad = Math.max(3, sw * 2);
        const width = ctx.measureText(text).width + pad * 2;
        const height = Math.max(18, sw * 8);
        const x = Math.max(0, Math.min(img.width - width, b[0]));
        const y = Math.max(height, b[1]);
        ctx.fillStyle = warn;
        ctx.fillRect(x, y - height, width, height);
        ctx.fillStyle = "#ffffff";
        ctx.fillText(text, x + pad, y - pad);
      }
    };
    if (profile === "baseline") {
      if (!evictedOnly) {
        targets
          .filter((target) => present.has(target.text))
          .forEach((target) => draw(target.text, target.baseline_box, accent));
      }
      if (showMissing || evictedOnly) {
        missing.forEach((target) => draw(target.text, target.baseline_box, err));
      }
    } else if (!evictedOnly) {
      labels.forEach((label) => {
        const text = asText(label.text);
        if (text && present.has(text)) draw(text, label.box, accent);
      });
    }
  }, [img, targets, present, missing, labels, selected, showBoxes, showMissing, evictedOnly, wrapperRef, profile, onDimensions]);
  useEffect(() => { if (canvasRef.current) onCanvasReady?.(canvasRef.current); }, [onCanvasReady]);
  /* No inline width/height on purpose: the caller's max-* classes scale the canvas
     down and the browser preserves the capture's intrinsic aspect ratio. Setting
     both dimensions explicitly would let max-width and max-height clamp each axis
     independently, which stretches the screenshot. */
  return (
    <canvas
      id={`canvas-${id}`}
      ref={canvasRef}
      hidden={hidden}
      className={className}
      style={style}
      onClick={(event) => {
        if (!img || !imageIsDrawable(img)) return;
        const rect = event.currentTarget.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / rect.width) * img.width;
        const y = ((event.clientY - rect.top) / rect.height) * img.height;
        const targetTexts = new Set(targets.map((target) => target.text));
        const hit = profile === "baseline"
          ? (evictedOnly ? missing : targets).find((target) => {
              const box = target.baseline_box;
              return box && x >= box[0] && x <= box[2] && y >= box[1] && y <= box[3];
            })
          : (!evictedOnly ? labels : []).map((label) => ({
              text: asText(label.text),
              box: label.box,
            })).find((label) => {
              const box = label.box;
              return Boolean(label.text && targetTexts.has(label.text) && box && x >= box[0] && x <= box[2] && y >= box[1] && y <= box[3]);
            });
        if (hit?.text) onSelect(hit.text);
      }}
    />
  );
}
