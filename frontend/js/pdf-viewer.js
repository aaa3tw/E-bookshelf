// Acrobat PDF 閱讀與互動引擎 (整合 PDF.js)

const PDFViewerModule = (() => {
  let pdfDoc = null;
  let pageNum = 1;
  let pageRendering = false;
  let pageNumPending = null;
  let scale = 1.25;
  let rotation = 0;
  let currentBook = null;

  const canvas = document.getElementById('pdfCanvas');
  const ctx = canvas.getContext('2d');
  const textLayerDiv = document.getElementById('pdfTextLayer');
  const pdfContainer = document.getElementById('pdfContainer');
  const epubContainer = document.getElementById('epubContainer');
  const pageInput = document.getElementById('currentPageInput');
  const totalPagesSpan = document.getElementById('totalPagesSpan');
  const zoomText = document.getElementById('zoomLevelText');
  const progressText = document.getElementById('readingProgressText');
  const locationText = document.getElementById('readingLocationText');

  // 初始化 pdf.js worker
  if (window.pdfjsLib) {
    pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
  }

  // 載入 PDF
  async function loadPdf(book) {
    currentBook = book;
    pdfContainer.classList.remove('hidden');
    epubContainer.classList.add('hidden');

    const fileUrl = `/api/books/${book.id}/file`;
    const loadingTask = pdfjsLib.getDocument({
      url: fileUrl,
      cMapUrl: 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/cmaps/',
      cMapPacked: true
    });

    try {
      pdfDoc = await loadingTask.promise;
      totalPagesSpan.innerText = pdfDoc.numPages;

      // 恢復上次閱讀進度
      pageNum = parseInt(book.last_location) || 1;
      if (pageNum > pdfDoc.numPages) pageNum = 1;

      renderPage(pageNum);
      renderOutline(book.outline);
      renderThumbnails(pdfDoc.numPages);
      setupControls();
    } catch (err) {
      console.error('Error loading PDF document:', err);
      alert('無法載入 PDF 文件');
    }
  }

  // 渲染指定頁面
  async function renderPage(num) {
    pageRendering = true;
    pageNum = num;
    pageInput.value = num;
    locationText.innerText = `位置: 第 ${num} 頁`;

    const progress = Math.round((num / pdfDoc.numPages) * 100);
    progressText.innerText = `進度: ${progress}%`;
    saveReadingProgress(num, progress);

    const page = await pdfDoc.getPage(num);
    const viewport = page.getViewport({ scale: scale, rotation: rotation });

    canvas.height = viewport.height;
    canvas.width = viewport.width;
    pdfContainer.style.width = `${viewport.width}px`;
    pdfContainer.style.height = `${viewport.height}px`;

    // 渲染 PDF Canvas
    const renderContext = {
      canvasContext: ctx,
      viewport: viewport
    };

    const renderTask = page.render(renderContext);
    await renderTask.promise;

    // 渲染 Text Layer (支援文字選取與高亮)
    textLayerDiv.innerHTML = '';
    textLayerDiv.style.width = `${viewport.width}px`;
    textLayerDiv.style.height = `${viewport.height}px`;
    textLayerDiv.style.setProperty('--scale-factor', viewport.scale);

    try {
      const textContent = await page.getTextContent();
      const textLayerTask = pdfjsLib.renderTextLayer({
        textContentSource: textContent,
        container: textLayerDiv,
        viewport: viewport,
        textDivs: []
      });
      if (textLayerTask && textLayerTask.promise) {
        await textLayerTask.promise;
      }
    } catch (e) {
      console.warn('Text layer render error:', e);
    }

    // 重新調整標註畫布
    AnnotationModule.syncCanvasSize(viewport.width, viewport.height, num);

    pageRendering = false;
    if (pageNumPending !== null) {
      renderPage(pageNumPending);
      pageNumPending = null;
    }

    // 高亮側邊欄縮圖當前頁
    highlightCurrentThumbnail(num);
  }

  function queueRenderPage(num) {
    if (window.hideSelectionQuickBar) window.hideSelectionQuickBar();
    if (pageRendering) {
      pageNumPending = num;
    } else {
      renderPage(num);
    }
  }

  function prevPage() {
    if (pageNum <= 1) return;
    pageNum--;
    queueRenderPage(pageNum);
  }

  function nextPage() {
    if (!pdfDoc || pageNum >= pdfDoc.numPages) return;
    pageNum++;
    queueRenderPage(pageNum);
  }

  function goToPage(num) {
    if (!pdfDoc) return;
    const p = Math.max(1, Math.min(num, pdfDoc.numPages));
    queueRenderPage(p);
  }

  // 縮放控制
  function zoomIn() {
    scale = Math.min(3.0, scale + 0.15);
    updateZoomDisplay();
    queueRenderPage(pageNum);
  }

  function zoomOut() {
    scale = Math.max(0.5, scale - 0.15);
    updateZoomDisplay();
    queueRenderPage(pageNum);
  }

  function updateZoomDisplay() {
    zoomText.innerText = `${Math.round(scale * 100)}%`;
  }

  function rotate() {
    rotation = (rotation + 90) % 360;
    queueRenderPage(pageNum);
  }

  // 側邊欄：渲染目錄大綱
  function renderOutline(outline) {
    const container = document.getElementById('outlineTreeContainer');
    container.innerHTML = '';

    if (!outline || outline.length === 0) {
      container.innerHTML = '<div class="text-slate-500 py-4 text-center">本文件無目錄結構</div>';
      return;
    }

    outline.forEach(item => {
      const node = document.createElement('div');
      const indent = (item.level - 1) * 12;
      node.className = 'toc-item py-1.5 px-2 rounded cursor-pointer transition text-slate-300 hover:text-white flex items-center justify-between';
      node.style.paddingLeft = `${Math.max(6, indent)}px`;

      node.innerHTML = `
        <span class="truncate pr-2">${item.title}</span>
        <span class="text-[10px] text-slate-500 font-mono">${item.page}</span>
      `;

      node.addEventListener('click', () => {
        goToPage(parseInt(item.page));
      });

      container.appendChild(node);
    });
  }

  // 側邊欄：渲染頁面微縮圖
  function renderThumbnails(total) {
    const container = document.getElementById('thumbnailsContainer');
    container.innerHTML = '';

    for (let i = 1; i <= total; i++) {
      const thumbBox = document.createElement('div');
      thumbBox.id = `thumb-page-${i}`;
      thumbBox.className = 'thumb-card flex flex-col items-center bg-[#1c1d1f] p-1.5 rounded border border-[#33373a] hover:border-red-500 cursor-pointer transition';

      thumbBox.innerHTML = `
        <div class="w-full aspect-[1/1.4] bg-[#2a2d2e] rounded overflow-hidden flex items-center justify-center text-slate-600">
          <img src="/api/books/${currentBook.id}/thumbnails/${i}" 
               loading="lazy" 
               class="w-full h-full object-contain"
               onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
          <span style="display:none;" class="text-[10px]">P.${i}</span>
        </div>
        <span class="text-[10px] text-slate-400 mt-1 font-mono">${i}</span>
      `;

      thumbBox.addEventListener('click', () => {
        goToPage(i);
      });

      container.appendChild(thumbBox);
    }
  }

  function highlightCurrentThumbnail(p) {
    document.querySelectorAll('.thumb-card').forEach(c => c.classList.remove('ring-2', 'ring-red-500', 'bg-slate-700'));
    const curr = document.getElementById(`thumb-page-${p}`);
    if (curr) {
      curr.classList.add('ring-2', 'ring-red-500', 'bg-slate-700');
      curr.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  // 儲存進度至後端
  async function saveReadingProgress(page, progress) {
    if (!currentBook) return;
    try {
      await fetch(`/api/books/${currentBook.id}/progress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          progress: progress,
          last_location: String(page)
        })
      });
    } catch (e) {
      console.warn('Failed to update progress', e);
    }
  }

  // 控制項按鈕綁定
  let controlsSetup = false;
  function setupControls() {
    if (controlsSetup) return;
    controlsSetup = true;

    document.getElementById('prevPageBtn').addEventListener('click', prevPage);
    document.getElementById('nextPageBtn').addEventListener('click', nextPage);
    pageInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const val = parseInt(pageInput.value);
        if (!isNaN(val)) goToPage(val);
      }
    });

    document.getElementById('zoomInBtn').addEventListener('click', zoomIn);
    document.getElementById('zoomOutBtn').addEventListener('click', zoomOut);
    document.getElementById('rotateBtn').addEventListener('click', rotate);
  }

  return {
    loadPdf,
    goToPage,
    nextPage,
    prevPage,
    getCurrentPage: () => pageNum,
    getScale: () => scale
  };
})();

