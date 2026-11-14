// Acrobat 標記與編輯器 (Annotation & Editing Engine)

const AnnotationModule = (() => {
  let currentBookId = null;
  let activeTool = 'hand'; // hand, select, highlight, pen, note, eraser
  let highlightColor = '#facc15';
  let annotations = []; // 本書所有註解
  let isDrawing = false;
  let currentStroke = [];
  let pendingSelection = null;

  const canvas = document.getElementById('annotationCanvas');
  const ctx = canvas.getContext('2d');
  const pdfContainer = document.getElementById('pdfContainer');
  const container = document.getElementById('annotationsListContainer');
  const floatingNoteBox = document.getElementById('floatingNoteBox');
  const floatingNoteText = document.getElementById('floatingNoteText');
  const quickBar = document.getElementById('selectionQuickBar');
  let pendingNotePoint = null;

  function init() {
    setupToolboxButtons();
    setupCanvasEvents();
    setupTextSelectionListener();
    setupQuickBarEvents();
    setupExportPdf();
  }

  // 載入註解
  async function loadAnnotations(bookId) {
    currentBookId = bookId;
    try {
      const res = await fetch(`/api/books/${bookId}/annotations`);
      annotations = await res.json();
      renderAnnotationsList();
      redrawCurrentPageAnnotations();
    } catch (err) {
      console.error('Failed to load annotations:', err);
    }
  }

  // 同步標註畫布尺寸
  function syncCanvasSize(width, height, pageNum) {
    canvas.width = width;
    canvas.height = height;
    redrawCurrentPageAnnotations();
  }

  // 重繪當前頁的所有標註與手繪塗鴉
  function redrawCurrentPageAnnotations() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!AppState.currentBook) return;

    // 清除舊的 DOM 便籤圖釘
    document.querySelectorAll('.sticky-pin').forEach(el => el.remove());

    const currPage = AppState.currentBook.file_type === 'pdf' ? 
      PDFViewerModule.getCurrentPage() : 1;

    const pageAnns = annotations.filter(a => a.page_index === currPage);

    pageAnns.forEach(ann => {
      // 螢光筆高亮 (半透明螢光效果)
      if (ann.type === 'highlight' && ann.data && ann.data.rects) {
        ctx.save();
        ctx.globalAlpha = 0.45;
        ctx.fillStyle = ann.color || '#facc15';
        ann.data.rects.forEach(r => {
          ctx.fillRect(r.x, r.y, r.width, r.height);
        });
        ctx.restore();
      }
      // 手繪畫筆塗鴉
      else if (ann.type === 'drawing' && ann.data && ann.data.points) {
        ctx.save();
        ctx.strokeStyle = ann.color || '#ef4444';
        ctx.lineWidth = ann.data.lineWidth || 3;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.beginPath();
        const pts = ann.data.points;
        if (pts.length > 0) {
          ctx.moveTo(pts[0].x, pts[0].y);
          for (let i = 1; i < pts.length; i++) {
            ctx.lineTo(pts[i].x, pts[i].y);
          }
          ctx.stroke();
        }
        ctx.restore();
      }
      // 便籤圖標
      else if (ann.type === 'note' && ann.data && ann.data.point) {
        createStickyPin(ann);
      }
    });
  }

  // 建立便籤視覺圖釘
  function createStickyPin(ann) {
    const pin = document.createElement('div');
    pin.className = 'sticky-pin';
    pin.style.left = `${ann.data.point.x}px`;
    pin.style.top = `${ann.data.point.y}px`;
    pin.title = ann.text_content || '便籤筆記';
    pin.innerHTML = '<i data-lucide="message-square" class="w-3 h-3"></i>';

    pin.addEventListener('click', (e) => {
      e.stopPropagation();
      showFloatingNoteAt(ann.data.point.x, ann.data.point.y, ann.text_content, ann.id);
    });

    pdfContainer.appendChild(pin);
    lucide.createIcons();
  }

  // 渲染側邊欄註解清單
  function renderAnnotationsList() {
    container.innerHTML = '';
    if (annotations.length === 0) {
      container.innerHTML = '<div class="text-center py-8 text-slate-500">本文件尚無任何標記與筆記</div>';
      return;
    }

    annotations.forEach(ann => {
      const item = document.createElement('div');
      item.className = 'p-2 rounded bg-[#1c1d1f] border border-[#33373a] hover:border-slate-500 text-xs flex flex-col gap-1 transition';

      const typeLabel = {
        highlight: '螢光筆高亮',
        drawing: '手繪塗鴉',
        note: '便籤筆記'
      }[ann.type] || ann.type;

      item.innerHTML = `
        <div class="flex items-center justify-between">
          <span class="font-bold text-slate-300 flex items-center gap-1">
            <span class="w-2.5 h-2.5 rounded-full inline-block" style="background-color: ${ann.color || '#facc15'}"></span>
            ${typeLabel}
          </span>
          <span class="text-[10px] text-slate-500 font-mono">P.${ann.page_index}</span>
        </div>
        ${ann.text_content ? `<p class="text-slate-300 italic line-clamp-2 bg-[#25282a] p-1 rounded">"${ann.text_content}"</p>` : ''}
        <div class="flex justify-end gap-2 pt-1 border-t border-[#2a2d2e]">
          <button class="btn-goto-ann text-emerald-400 hover:text-emerald-300 text-[10px] flex items-center gap-0.5">
            <i data-lucide="corner-down-right" class="w-2.5 h-2.5"></i>前往
          </button>
          <button class="btn-del-ann text-red-400 hover:text-red-300 text-[10px]">刪除</button>
        </div>
      `;

      item.querySelector('.btn-goto-ann').addEventListener('click', () => {
        if (AppState.currentBook.file_type === 'pdf') {
          PDFViewerModule.goToPage(ann.page_index);
        }
      });

      item.querySelector('.btn-del-ann').addEventListener('click', async () => {
        if (confirm('確定要刪除這筆註解嗎？')) {
          await deleteAnnotation(ann.id);
        }
      });

      container.appendChild(item);
    });

    lucide.createIcons();
  }

  // 儲存新註解至後端
  async function saveAnnotation(type, data, text_content = '', color = highlightColor) {
    const pageIndex = AppState.currentBook.file_type === 'pdf' ? 
      PDFViewerModule.getCurrentPage() : 1;

    try {
      const res = await fetch(`/api/books/${currentBookId}/annotations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          page_index: pageIndex,
          type: type,
          color: color,
          data: data,
          text_content: text_content
        })
      });

      if (res.ok) {
        await loadAnnotations(currentBookId);
      }
    } catch (err) {
      console.error('Failed to save annotation:', err);
    }
  }

  // 刪除註解
  async function deleteAnnotation(annId) {
    try {
      await fetch(`/api/books/${currentBookId}/annotations/${annId}`, {
        method: 'DELETE'
      });
      await loadAnnotations(currentBookId);
    } catch (err) {
      console.error('Failed to delete annotation:', err);
    }
  }

  // 全域快捷浮動選單顯示與防遮擋自動關閉控制器
  let quickBarTimer = null;

  function hideQuickBar() {
    if (quickBarTimer) {
      clearTimeout(quickBarTimer);
      quickBarTimer = null;
    }
    if (quickBar) {
      quickBar.classList.add('hidden');
      quickBar.style.display = 'none';
      quickBar.style.opacity = '0';
      quickBar.style.pointerEvents = 'none';
    }
    // 僅在非輸入框焦點時清除頁面文字反白選取 (避免清除輸入框的文字游標 caret)
    try {
      const activeTag = (document.activeElement && document.activeElement.tagName) ? document.activeElement.tagName.toUpperCase() : '';
      const isInput = activeTag === 'INPUT' || activeTag === 'TEXTAREA' || document.activeElement?.isContentEditable;
      if (!isInput && window.getSelection) {
        window.getSelection().removeAllRanges();
      }
    } catch (e) {}

    try {
      if (window.currentEpubSelection && window.currentEpubSelection.contents) {
        const cWin = window.currentEpubSelection.contents.window;
        if (cWin && cWin.getSelection) {
          cWin.getSelection().removeAllRanges();
        }
      }
    } catch (e) {}

    pendingSelection = null;
    window.currentEpubSelection = null;
  }

  function showQuickBarAt(x, y, autoDismissSec = 2.5) {
    if (!quickBar) return;
    if (quickBarTimer) {
      clearTimeout(quickBarTimer);
      quickBarTimer = null;
    }

    const mainArea = document.getElementById('viewerMainArea');
    const mainRect = mainArea ? mainArea.getBoundingClientRect() : { width: window.innerWidth, height: window.innerHeight };
    const barWidth = 220;
    const barHeight = 42;

    // 視窗邊界限制防溢出與防截斷 (以 viewerMainArea 範圍為準)
    const clampedX = Math.max(8, Math.min(mainRect.width - barWidth - 8, x));
    const clampedY = Math.max(8, Math.min(mainRect.height - barHeight - 8, y));

    quickBar.style.left = `${clampedX}px`;
    quickBar.style.top = `${clampedY}px`;
    quickBar.style.display = 'flex';
    quickBar.style.opacity = '1';
    quickBar.style.pointerEvents = 'auto';
    quickBar.classList.remove('hidden');

    if (window.lucide) lucide.createIcons();

    // 關鍵：選取後啟動自動關閉計時 (預設 2.5 秒自動關閉，防遮擋視線)
    quickBarTimer = setTimeout(() => {
      hideQuickBar();
    }, autoDismissSec * 1000);
  }

  // 匯出至全域供 EPUB/PDF 共用
  window.hideSelectionQuickBar = hideQuickBar;
  window.showSelectionQuickBar = showQuickBarAt;

  // 監聽文字框選反白 (Text Selection)
  function setupTextSelectionListener() {
    document.addEventListener('mouseup', async (e) => {
      // 點擊快捷浮動列內部或便籤盒時不重複觸發
      if (e.target.closest('#selectionQuickBar') || e.target.closest('#floatingNoteBox')) return;

      const sel = window.getSelection();
      const text = sel ? sel.toString().trim() : '';

      if (!text || sel.isCollapsed) {
        hideQuickBar();
        return;
      }

      // 檢查是否選取在 PDF 文字層內
      const range = sel.getRangeAt(0);
      const containerNode = range.commonAncestorContainer;
      const isInsidePdf = pdfContainer.contains(containerNode);

      if (!isInsidePdf) {
        // 非 PDF 區域選取，交由其他閱讀器或關閉
        return;
      }

      // 計算選取座標
      const clientRects = range.getClientRects();
      const containerRect = pdfContainer.getBoundingClientRect();
      const rects = [];

      for (let i = 0; i < clientRects.length; i++) {
        const r = clientRects[i];
        rects.push({
          x: r.left - containerRect.left,
          y: r.top - containerRect.top,
          width: r.width,
          height: r.height
        });
      }

      pendingSelection = {
        text: text,
        rects: rects,
        firstRect: clientRects[0]
      };

      // 如果當前啟用的是「螢光筆」模式，直接自動完成高亮！
      if (activeTool === 'highlight') {
        await saveAnnotation('highlight', { rects }, text, highlightColor);
        sel.removeAllRanges();
        hideQuickBar();
        return;
      }

      // 如果當前是「選取工具」或「手形」，彈出 Acrobat 快捷操作列
      if (activeTool === 'select' || activeTool === 'hand') {
        const first = clientRects[0];
        const barX = first.left + (first.width / 2) - 90;
        const barY = first.top - 44;
        showQuickBarAt(barX, barY, 3.5);
      }
    });
  }

  // 快捷浮動選單操作
  function setupQuickBarEvents() {
    // 滑鼠移入暫停自動關閉，移出後重啟 1.5 秒自動關閉
    quickBar.addEventListener('mouseenter', () => {
      if (quickBarTimer) {
        clearTimeout(quickBarTimer);
        quickBarTimer = null;
      }
    });

    quickBar.addEventListener('mouseleave', () => {
      if (!quickBar.classList.contains('hidden')) {
        if (quickBarTimer) clearTimeout(quickBarTimer);
        quickBarTimer = setTimeout(() => {
          hideQuickBar();
        }, 800);
      }
    });

    // 關閉按鈕 (✕) - 支援 click / pointerdown / mousedown 多重保障
    const quickCloseBtn = document.getElementById('quickCloseBtn');
    if (quickCloseBtn) {
      const doClose = (e) => {
        e.stopPropagation();
        e.preventDefault();
        hideQuickBar();
      };
      quickCloseBtn.addEventListener('click', doClose);
      quickCloseBtn.addEventListener('pointerdown', doClose);
      quickCloseBtn.addEventListener('mousedown', doClose);
    }

    // 快捷高亮按鈕
    document.getElementById('quickHighlightBtn').addEventListener('click', async (e) => {
      e.stopPropagation();
      // 1. 若為 PDF 選取
      if (pendingSelection && pendingSelection.rects && pendingSelection.rects.length > 0) {
        await saveAnnotation('highlight', { rects: pendingSelection.rects }, pendingSelection.text, highlightColor);
        window.getSelection()?.removeAllRanges();
      }
      // 2. 若為 EPUB 選取
      else if (window.currentEpubSelection && window.EPUBViewerModule && window.EPUBViewerModule.highlightSelection) {
        window.EPUBViewerModule.highlightSelection(window.currentEpubSelection);
      }
      hideQuickBar();
    });

    // 快捷建立多重書籤
    document.getElementById('quickAddBmFromSelBtn').addEventListener('click', (e) => {
      e.stopPropagation();
      const selectedText = (pendingSelection && pendingSelection.text) || 
                           (window.currentEpubSelection && window.currentEpubSelection.text) || '';
      hideQuickBar();
      if (window.BookmarkModule && window.BookmarkModule.openAddBookmarkModal) {
        window.BookmarkModule.openAddBookmarkModal(selectedText);
      }
    });

    // 快捷複製
    document.getElementById('quickCopyBtn').addEventListener('click', (e) => {
      e.stopPropagation();
      const selectedText = (pendingSelection && pendingSelection.text) || 
                           (window.currentEpubSelection && window.currentEpubSelection.text) || '';
      if (selectedText) {
        navigator.clipboard.writeText(selectedText);
      }
      hideQuickBar();
    });

    // 閱讀防遮擋：點擊畫面外部關閉快捷選取工具列 (防干擾輸入框與文字游標)
    const handleOutsideDismiss = (e) => {
      // 若 quickBar 本來就沒有顯示，直接返回，絕不干擾正常的點擊與文字輸入
      if (!quickBar || quickBar.classList.contains('hidden') || quickBar.style.display === 'none') {
        return;
      }
      // 點擊快捷列本身或便籤筆記方塊內部時不關閉
      if (e.target && (e.target.closest('#selectionQuickBar') || e.target.closest('#floatingNoteBox'))) {
        return;
      }
      hideQuickBar();
    };

    // 採用常規冒泡事件，避免捕獲階段搶先清空 input 游標
    document.addEventListener('pointerdown', handleOutsideDismiss);
    document.addEventListener('click', handleOutsideDismiss);

    window.addEventListener('wheel', () => {
      if (quickBar && !quickBar.classList.contains('hidden')) hideQuickBar();
    }, { passive: true });
    window.addEventListener('scroll', () => {
      if (quickBar && !quickBar.classList.contains('hidden')) hideQuickBar();
    }, { passive: true });
    window.addEventListener('blur', hideQuickBar);
    document.getElementById('viewerMainArea')?.addEventListener('scroll', () => {
      if (quickBar && !quickBar.classList.contains('hidden')) hideQuickBar();
    }, { passive: true });
    document.getElementById('pdfContainer')?.addEventListener('scroll', () => {
      if (quickBar && !quickBar.classList.contains('hidden')) hideQuickBar();
    }, { passive: true });
    document.getElementById('epubContainer')?.addEventListener('scroll', () => {
      if (quickBar && !quickBar.classList.contains('hidden')) hideQuickBar();
    }, { passive: true });

    window.addEventListener('keydown', (e) => {
      // 若使用者正在輸入框或文字區塊打字，絕不觸發 quickBar 關閉或清除選取
      const tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : '';
      if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target?.isContentEditable) {
        return;
      }
      if (quickBar && !quickBar.classList.contains('hidden')) {
        if (e.key === 'Escape' || ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', ' '].includes(e.key)) {
          hideQuickBar();
        }
      }
    });
  }

  // 設置畫布手繪塗鴉與便籤事件
  function setupCanvasEvents() {
    canvas.addEventListener('mousedown', (e) => {
      if (activeTool === 'pen') {
        isDrawing = true;
        const rect = canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        currentStroke = [{ x, y }];
      } else if (activeTool === 'note') {
        const rect = canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        showFloatingNoteAt(x, y);
      }
    });

    canvas.addEventListener('mousemove', (e) => {
      if (!isDrawing || activeTool !== 'pen') return;
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      currentStroke.push({ x, y });

      ctx.strokeStyle = highlightColor;
      ctx.lineWidth = 3;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.beginPath();
      const last = currentStroke[currentStroke.length - 2];
      ctx.moveTo(last.x, last.y);
      ctx.lineTo(x, y);
      ctx.stroke();
    });

    window.addEventListener('mouseup', async () => {
      if (isDrawing && activeTool === 'pen') {
        isDrawing = false;
        if (currentStroke.length >= 2) {
          await saveAnnotation('drawing', { points: currentStroke, lineWidth: 3 }, '手繪標記', highlightColor);
        }
        currentStroke = [];
      }
    });
  }

  // 顯示浮動便籤編輯器
  function showFloatingNoteAt(x, y, existingText = '', existingId = null) {
    pendingNotePoint = { x, y, id: existingId };
    floatingNoteBox.style.left = `${Math.min(x + 10, window.innerWidth - 300)}px`;
    floatingNoteBox.style.top = `${y + 10}px`;
    floatingNoteText.value = existingText;
    floatingNoteBox.classList.remove('hidden');
    floatingNoteText.focus();
  }

  // 工具箱按鈕與圖層事件穿透設定 (關鍵核心修復)
  function setupToolboxButtons() {
    const tools = [
      { id: 'toolHand', name: 'hand' },
      { id: 'toolSelect', name: 'select' },
      { id: 'toolHighlight', name: 'highlight' },
      { id: 'toolPen', name: 'pen' },
      { id: 'toolNote', name: 'note' },
      { id: 'toolEraser', name: 'eraser' }
    ];

    tools.forEach(t => {
      const btn = document.getElementById(t.id);
      if (!btn) return;
      btn.addEventListener('click', () => {
        tools.forEach(other => {
          document.getElementById(other.id)?.classList.remove('active');
        });
        btn.classList.add('active');
        activeTool = t.name;

        // 核心設定：讓選取與螢光筆完全能穿透到文字層
        if (activeTool === 'pen' || activeTool === 'eraser' || activeTool === 'note') {
          canvas.style.pointerEvents = 'auto';
          pdfContainer.style.cursor = activeTool === 'note' ? 'cell' : 'crosshair';
        } else if (activeTool === 'highlight') {
          canvas.style.pointerEvents = 'none';
          pdfContainer.style.cursor = 'crosshair';
        } else if (activeTool === 'select') {
          canvas.style.pointerEvents = 'none';
          pdfContainer.style.cursor = 'text';
        } else {
          canvas.style.pointerEvents = 'none';
          pdfContainer.style.cursor = 'grab';
        }
      });
    });

    // 顏色選擇器
    document.querySelectorAll('.color-picker-dot').forEach(dot => {
      dot.addEventListener('click', () => {
        highlightColor = dot.dataset.color;
        document.getElementById('currentColorDot').style.backgroundColor = highlightColor;
      });
    });

    // 便籤儲存與關閉
    document.getElementById('closeFloatingNoteBtn').addEventListener('click', () => {
      floatingNoteBox.classList.add('hidden');
    });

    document.getElementById('saveFloatingNoteBtn').addEventListener('click', async () => {
      const text = floatingNoteText.value.trim();
      if (text && pendingNotePoint) {
        await saveAnnotation('note', { point: { x: pendingNotePoint.x, y: pendingNotePoint.y } }, text, '#f59e0b');
      }
      floatingNoteBox.classList.add('hidden');
    });

    // 清空本文件所有標記
    document.getElementById('clearAllAnnotationsBtn').addEventListener('click', async () => {
      if (confirm('確定要清空本書的所有註解與標記嗎？此操作不可逆。')) {
        for (const a of annotations) {
          await fetch(`/api/books/${currentBookId}/annotations/${a.id}`, { method: 'DELETE' });
        }
        await loadAnnotations(currentBookId);
      }
    });
  }

  // 導出帶註解之 PDF
  function setupExportPdf() {
    const exportBtn = document.getElementById('exportAnnotatedPdfBtn');
    if (exportBtn) {
      exportBtn.addEventListener('click', async () => {
        if (!AppState.currentBook || AppState.currentBook.file_type !== 'pdf') {
          alert('僅 PDF 檔案支援匯出帶標註文件');
          return;
        }
        try {
          const res = await fetch(`/api/books/${AppState.currentBook.id}/export-annotated-pdf`, { method: 'POST' });
          if (!res.ok) throw new Error('Export failed');
          const blob = await res.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `[已標註]_${AppState.currentBook.title}.pdf`;
          a.click();
          window.URL.revokeObjectURL(url);
        } catch (e) {
          console.error(e);
          alert('匯出帶標註 PDF 失敗');
        }
      });
    }
  }

  init();

  return {
    loadAnnotations,
    syncCanvasSize,
    redrawCurrentPageAnnotations,
    saveAnnotation
  };
})();
