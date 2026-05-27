/**
 * 在 canvas 上绘制切题框与批注
 */
const ResultCanvas = (() => {
  function drawBoxes(canvas, imageSrc, questions, options = {}) {
    const { showScores = true } = options;
    const ctx = canvas.getContext('2d');
    const img = new Image();

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('图像加载超时')), 15000);

      img.onload = () => {
        clearTimeout(timeout);
        const maxW = canvas.parentElement?.clientWidth || 640;
        const scale = Math.min(1, maxW / img.width);
        canvas.width = img.width * scale;
        canvas.height = img.height * scale;

        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

        const sx = canvas.width / img.width;
        const sy = canvas.height / img.height;

        (questions || []).forEach((q, i) => {
          const box = normalizeBbox(q.bbox, q.points);
          if (!box) return;

          const x = box.x * sx;
          const y = box.y * sy;
          const w = box.width * sx;
          const h = box.height * sy;

          const color = statusColor(q.status);
          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          ctx.strokeRect(x, y, w, h);

          ctx.fillStyle = color;
          ctx.globalAlpha = 0.12;
          ctx.fillRect(x, y, w, h);
          ctx.globalAlpha = 1;

          const label = `${q.order ?? i + 1}`;
          ctx.fillStyle = color;
          ctx.fillRect(x, y - 22, 28, 22);
          ctx.fillStyle = '#fff';
          ctx.font = 'bold 13px system-ui, sans-serif';
          ctx.fillText(label, x + 8, y - 6);

          if (showScores && q.score != null) {
            const scoreText = `${q.score}分`;
            ctx.font = 'bold 14px system-ui, sans-serif';
            const tw = ctx.measureText(scoreText).width;
            const tx = x + w + 6;
            const ty = y + 14;
            ctx.fillStyle = color;
            ctx.fillRect(tx, ty - 14, tw + 10, 20);
            ctx.fillStyle = '#fff';
            ctx.fillText(scoreText, tx + 5, ty);
          }
        });

        resolve();
      };
      img.onerror = () => {
        clearTimeout(timeout);
        reject(new Error('图像加载失败'));
      };
      img.src = imageSrc;
    });
  }

  function normalizeBbox(bbox, points) {
    if (bbox && typeof bbox.x === 'number') {
      return bbox;
    }
    if (Array.isArray(points) && points.length >= 4) {
      const xs = points.map((p) => p[0] ?? p.x);
      const ys = points.map((p) => p[1] ?? p.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
    }
    return null;
  }

  function statusColor(status) {
    const map = {
      correct: '#22c55e',
      wrong: '#ef4444',
      partial: '#f59e0b',
      ocr_failed: '#94a3b8',
      need_review: '#94a3b8',
    };
    return map[status] || '#3b82f6';
  }

  return { drawBoxes, statusColor };
})();
