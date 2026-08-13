function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function exportCanvasAsPng(canvas: HTMLCanvasElement, filename: string) {
  canvas.toBlob((blob) => {
    if (blob) download(blob, filename);
  });
}

export function exportCanvasPairAsPng(
  bottom: HTMLCanvasElement,
  top: HTMLCanvasElement,
  filename: string,
) {
  const canvas = document.createElement("canvas");
  canvas.width = bottom.width;
  canvas.height = bottom.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.drawImage(bottom, 0, 0);
  ctx.drawImage(
    top,
    0,
    0,
    top.width,
    top.height,
    0,
    0,
    bottom.width,
    bottom.height,
  );
  exportCanvasAsPng(canvas, filename);
}

export function exportSvgAsPng(
  svg: SVGSVGElement,
  filename: string,
  options: { background?: string; title?: string } = {},
) {
  const box = svg.viewBox.baseVal;
  const width = box.width || svg.clientWidth || 760;
  const height = box.height || svg.clientHeight || 400;
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
  style.textContent = Array.from(document.styleSheets)
    .flatMap((sheet) => {
      try {
        return Array.from(sheet.cssRules).map((rule) => rule.cssText);
      } catch {
        return [];
      }
    })
    .join("\n");
  clone.insertBefore(style, clone.firstChild);
  if (options.title) {
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = options.title;
    clone.insertBefore(title, clone.firstChild);
  }
  const xml = new XMLSerializer().serializeToString(clone);
  const url = URL.createObjectURL(
    new Blob([xml], { type: "image/svg+xml" }),
  );
  const img = new Image();

  img.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = width * 2;
    canvas.height = height * 2;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.scale(2, 2);
      if (options.background) {
        ctx.fillStyle = options.background;
        ctx.fillRect(0, 0, width, height);
      }
      ctx.drawImage(img, 0, 0, width, height);
      exportCanvasAsPng(canvas, filename);
    }
    URL.revokeObjectURL(url);
  };
  img.onerror = () => URL.revokeObjectURL(url);
  img.src = url;
}
