// Acrobat EPUB 閱讀與章節線上編輯引擎 (強化版 ePub.js 整合)

const EPUBViewerModule = (() => {
  let bookInstance = null;
  let rendition = null;
  let currentBook = null;
  let currentFontSize = 100;
  let currentTheme = 'white';
  let chaptersData = [];
  let isPlainTextMode = true; // 預設提供友善的純文字段落編輯模式

  const epubContainer = document.getElementById('epubContainer');
  const pdfContainer = document.getElementById('pdfContainer');
  const viewerArea = document.getElementById('epubViewerArea');
  const loadingOverlay = document.getElementById('epubLoadingOverlay');
  const progressText = document.getElementById('readingProgressText');
  const locationText = document.getElementById('readingLocationText');
  const totalPagesSpan = document.getElementById('totalPagesSpan');
  const pageInput = document.getElementById('currentPageInput');
  const quickNavSelect = document.getElementById('epubQuickNavSelect');
  const chapterSelect = document.getElementById('epubChapterSelect');
  const chapterContentArea = document.getElementById('epubChapterContentArea');
  const toggleEditModeBtn = document.getElementById('toggleEditModeBtn');
  const quickBar = document.getElementById('selectionQuickBar');

  // 經典閱讀器色彩主題配置
  const THEME_STYLES = {
    white: {
      bodyBg: '#ffffff',
      textColor: '#1a202c',
      pColor: '#2d3748',
      hColor: '#0f172a'
    },
    sepia: {
      bodyBg: '#fbf0d9',
      textColor: '#423321',
      pColor: '#4f3c27',
      hColor: '#302416'
    },
    dark: {
      bodyBg: '#1e2022',
      textColor: '#e2e8f0',
      pColor: '#cbd5e1',
      hColor: '#f8fafc'
    }
  };

  async function loadEpub(book) {
    currentBook = book;
    pdfContainer.classList.add('hidden');
    epubContainer.classList.remove('hidden');
    loadingOverlay.classList.remove('hidden');
    viewerArea.innerHTML = '';

    // 銷毀舊實例
    if (rendition) {
      try { rendition.destroy(); } catch (e) {}
      rendition = null;
    }
    if (bookInstance) {
      try { bookInstance.destroy(); } catch (e) {}
      bookInstance = null;
    }

    try {
      // 1. 抓取 ArrayBuffer
      const fileUrl = `/api/books/${book.id}/file?t=${Date.now()}`;
      const resp = await fetch(fileUrl);
      if (!resp.ok) throw new Error('Failed to fetch EPUB binary file');
      const arrayBuffer = await resp.arrayBuffer();

      // 2. 初始化 ePub 實例
      bookInstance = ePub(arrayBuffer);

      // 3. 確保容器可見
      await new Promise(resolve => setTimeout(resolve, 80));

      // 4. 初始化 Rendition
      rendition = bookInstance.renderTo(viewerArea, {
        width: '100%',
        height: '100%',
        flow: 'paginated',
        spread: 'auto',
        allowScriptedContent: true
      });

      // 5. 註冊 hook：強制覆寫美化樣式 + 穿透綁定 iframe 內部鍵盤/點擊/滾動事件 (防止小視窗遮擋)
      rendition.hooks.content.register((contents) => {
        applyThemeStyles(contents);
        if (contents.document) {
          // 點擊或觸控 iframe 內部立即關閉浮動小視窗 (Capture 階段捕獲，徹底防殘留)
          const dismissEvents = ['pointerdown', 'mousedown', 'click', 'touchstart', 'wheel'];
          dismissEvents.forEach(evt => {
            contents.document.addEventListener(evt, () => {
              if (window.hideSelectionQuickBar) window.hideSelectionQuickBar();
            }, { capture: true, passive: true });
          });

          // 滾動 iframe 時立即關閉
          contents.window.addEventListener('scroll', () => {
            if (window.hideSelectionQuickBar) window.hideSelectionQuickBar();
          }, { passive: true });

          // 穿透綁定鍵盤翻頁與 Escape 關閉
          contents.document.addEventListener('keydown', (e) => {
            if (['Escape', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', ' '].includes(e.key)) {
              if (window.hideSelectionQuickBar) window.hideSelectionQuickBar();
            }
            if (window.handleGlobalPagingKey) {
              window.handleGlobalPagingKey(e);
            }
          }, true);
        }
      });

      // 6. 監聽文字選取 (精確計算相對座標，防遮擋視線，並在 2.5 秒無操作自動關閉)
      rendition.on('selected', (cfiRange, contents) => {
        const text = rendition.getRange(cfiRange).toString().trim();
        if (!text) {
          if (window.hideSelectionQuickBar) window.hideSelectionQuickBar();
          return;
        }
        window.currentEpubSelection = { cfiRange, text, contents };
        try {
          const sel = contents.window.getSelection();
          if (!sel || sel.rangeCount === 0) return;
          const rect = sel.getRangeAt(0).getBoundingClientRect();
          
          const mainArea = document.getElementById('viewerMainArea') || document.body;
          const mainRect = mainArea.getBoundingClientRect();
          const iframe = contents.document?.defaultView?.frameElement;
          const iframeRect = iframe ? iframe.getBoundingClientRect() : mainRect;

          // 相對於 viewerMainArea 容器的精準坐標
          let barX = (iframeRect.left - mainRect.left) + rect.left + (rect.width / 2) - 90;
          let barY = (iframeRect.top - mainRect.top) + rect.top - 44;

          // 若靠近上方邊界，改在選取區下方顯示，徹底防遮擋文字
          if (barY < 10) {
            barY = (iframeRect.top - mainRect.top) + rect.bottom + 8;
          }

          if (window.showSelectionQuickBar) {
            window.showSelectionQuickBar(barX, barY, 2.5);
          }
        } catch (err) {
          console.warn('選取定位異常:', err);
        }
      });

      // 7. 初始章節展示
      let initialLocation = undefined;
      if (book.last_location && book.last_location !== '1' && !book.last_location.startsWith('p')) {
        initialLocation = book.last_location;
      }

      try {
        await rendition.display(initialLocation);
      } catch (err) {
        await rendition.display();
      }

      // 8. 監聽翻頁與進度更新
      rendition.on('relocated', (location) => {
        if (window.hideSelectionQuickBar) window.hideSelectionQuickBar();
        if (location && location.start) {
          const cfi = location.start.cfi;
          locationText.innerText = `CFI: ${cfi.substring(0, 15)}...`;

          if (bookInstance.locations && bookInstance.locations.total > 0) {
            const percent = bookInstance.locations.percentageFromCfi(cfi);
            const progress = Math.round(percent * 100);
            progressText.innerText = `進度: ${progress}%`;
            saveReadingProgress(cfi, progress);
          } else {
            saveReadingProgress(cfi, 1);
          }
        }
      });

      // 9. 載入導航目錄
      bookInstance.loaded.navigation.then(nav => {
        renderEpubToc(nav.toc);
        populateQuickNav(nav.toc);
      }).catch(e => {
        fallbackSpineNavigation();
      });

      bookInstance.ready.then(() => {
        totalPagesSpan.innerText = 'EPUB';
        return bookInstance.locations.generate(1024);
      }).then(() => {
        if (rendition.currentLocation() && bookInstance.locations) {
          const p = Math.round(bookInstance.locations.percentageFromCfi(rendition.currentLocation().start.cfi) * 100);
          progressText.innerText = `進度: ${p}%`;
        }
      }).catch(err => {});

      // 10. 載入章節原始文字供「編輯」面板使用
      await loadEpubEditorChapters(book.id);

      setupControls();

    } catch (err) {
      console.error('Fatal error loading EPUB:', err);
      viewerArea.innerHTML = `
        <div class="h-full flex flex-col items-center justify-center p-8 text-center text-slate-700">
          <i data-lucide="alert-triangle" class="w-12 h-12 text-amber-500 mb-3"></i>
          <h3 class="text-base font-bold text-slate-800 mb-1">EPUB 內容渲染時發生問題</h3>
          <p class="text-xs text-slate-500 max-w-md">${err.message || '未知錯誤，請檢查檔案格式是否完整'}</p>
        </div>
      `;
      lucide.createIcons();
    } finally {
      loadingOverlay.classList.add('hidden');
    }
  }

  // 套用主題樣式至 EPUB 頁面
  function applyThemeStyles(contents) {
    const doc = contents.document;
    if (!doc) return;

    const theme = THEME_STYLES[currentTheme] || THEME_STYLES.white;
    const body = doc.body;

    if (body) {
      body.style.backgroundColor = `${theme.bodyBg} !important`;
      body.style.color = `${theme.textColor} !important`;
      body.style.fontFamily = '"Microsoft JhengHei", "PingFang TC", "Noto Sans TC", sans-serif';
      body.style.fontSize = `${currentFontSize}%`;
      body.style.lineHeight = '1.85';
      body.style.padding = '25px 35px';
      body.style.boxSizing = 'border-box';
    }

    const paragraphs = doc.querySelectorAll('p, div, span, li');
    paragraphs.forEach(p => {
      p.style.color = theme.pColor;
      p.style.lineHeight = '1.85';
    });

    const headings = doc.querySelectorAll('h1, h2, h3, h4, h5, h6');
    headings.forEach(h => {
      h.style.color = theme.hColor;
      h.style.fontWeight = 'bold';
    });
  }

  // 渲染目錄大綱
  function renderEpubToc(tocList) {
    const container = document.getElementById('outlineTreeContainer');
    container.innerHTML = '';

    if (!tocList || tocList.length === 0) {
      fallbackSpineNavigation();
      return;
    }

    function appendItems(items, level = 1) {
      items.forEach(item => {
        const node = document.createElement('div');
        node.className = 'toc-item py-1.5 px-2 rounded cursor-pointer transition text-slate-300 hover:text-white truncate flex items-center justify-between';
        node.style.paddingLeft = `${Math.max(6, level * 10)}px`;
        node.innerHTML = `
          <span class="truncate pr-1">${item.label ? item.label.trim() : '章節'}</span>
          <i data-lucide="chevron-right" class="w-3 h-3 text-slate-600 shrink-0"></i>
        `;

        node.addEventListener('click', () => {
          if (rendition && item.href) {
            rendition.display(item.href);
          }
        });
        container.appendChild(node);

        if (item.subitems && item.subitems.length > 0) {
          appendItems(item.subitems, level + 1);
        }
      });
    }

    appendItems(tocList);
    lucide.createIcons();
  }

  // 填充章節快速導航選單
  function populateQuickNav(tocList) {
    quickNavSelect.innerHTML = '';
    if (!tocList || tocList.length === 0) {
      quickNavSelect.innerHTML = '<option value="">第一章</option>';
      return;
    }

    tocList.forEach((item, idx) => {
      const opt = document.createElement('option');
      opt.value = item.href;
      opt.innerText = item.label ? item.label.trim() : `第 ${idx + 1} 章`;
      quickNavSelect.appendChild(opt);
    });

    quickNavSelect.onchange = (e) => {
      if (rendition && e.target.value) {
        rendition.display(e.target.value);
      }
    };
  }

  // 回退抽取章節
  function fallbackSpineNavigation() {
    const container = document.getElementById('outlineTreeContainer');
    container.innerHTML = '';
    quickNavSelect.innerHTML = '';

    if (!bookInstance || !bookInstance.spine || !bookInstance.spine.items) return;

    bookInstance.spine.items.forEach((item, idx) => {
      const node = document.createElement('div');
      node.className = 'toc-item py-1.5 px-2 rounded cursor-pointer transition text-slate-300 hover:text-white truncate';
      node.innerText = `章節 ${idx + 1}`;

      node.addEventListener('click', () => {
        if (rendition) rendition.display(item.href || idx);
      });
      container.appendChild(node);

      const opt = document.createElement('option');
      opt.value = item.href || idx;
      opt.innerText = `章節 ${idx + 1}`;
      quickNavSelect.appendChild(opt);
    });
  }

  // 載入章節原始文字供「編輯」面板使用
  async function loadEpubEditorChapters(bookId) {
    try {
      const res = await fetch(`/api/books/${bookId}/epub-chapters`);
      chaptersData = await res.json();
      
      chapterSelect.innerHTML = '';

      chaptersData.forEach((ch, idx) => {
        const opt = document.createElement('option');
        opt.value = ch.file_name;
        opt.innerText = ch.title || `章節 ${idx + 1}`;
        chapterSelect.appendChild(opt);
      });

      updateEditorContent();

      chapterSelect.onchange = () => {
        updateEditorContent();
      };

    } catch (err) {
      console.error('Error loading chapters for editing:', err);
    }
  }

  // 切換章節文字或原始碼更新編輯區
  function updateEditorContent() {
    const found = chaptersData.find(c => c.file_name === chapterSelect.value);
    if (found) {
      chapterContentArea.value = isPlainTextMode ? (found.plain_text || found.content) : found.content;
    }
  }

  // 儲存編輯後的 EPUB 章節內容 (一鍵同步回檔案並熱刷新畫面)
  async function saveCurrentEpubChapter() {
    const chapterFileName = chapterSelect.value;
    const content = chapterContentArea.value;

    if (!chapterFileName) {
      alert('請先選擇要編輯的章節');
      return;
    }

    try {
      const res = await fetch(`/api/books/${currentBook.id}/epub-chapters/${encodeURIComponent(chapterFileName)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      });

      if (res.ok) {
        alert('章節內容已成功編輯並儲存回 EPUB 檔案！正在重新載入畫面...');
        // 重新載入書籍以呈現最新修改
        await loadEpub(currentBook);
      } else {
        alert('儲存失敗，請檢查格式');
      }
    } catch (err) {
      console.error('Failed to save chapter:', err);
      alert('儲存失敗，請重試');
    }
  }

  function prevPage() {
    if (window.hideSelectionQuickBar) window.hideSelectionQuickBar();
    if (rendition) rendition.prev();
  }

  function nextPage() {
    if (window.hideSelectionQuickBar) window.hideSelectionQuickBar();
    if (rendition) rendition.next();
  }

  function goToLocation(cfi) {
    if (window.hideSelectionQuickBar) window.hideSelectionQuickBar();
    if (rendition) rendition.display(cfi);
  }

  // EPUB 高亮標記
  function highlightSelection(sel) {
    if (!rendition || !sel || !sel.cfiRange) return;
    try {
      rendition.annotations.add('highlight', sel.cfiRange, {}, (e) => {}, 'epub-highlight-mark', { fill: '#facc15' });
      sel.contents.window.getSelection()?.removeAllRanges();
    } catch (e) {
      console.warn('EPUB 高亮失敗:', e);
    }
  }

  function changeFontSize(delta) {
    currentFontSize = Math.max(70, Math.min(220, currentFontSize + delta));
    if (rendition) {
      rendition.getContents().forEach(contents => {
        applyThemeStyles(contents);
      });
    }
  }

  function setTheme(themeKey) {
    currentTheme = themeKey;
    const theme = THEME_STYLES[themeKey] || THEME_STYLES.white;
    epubContainer.style.backgroundColor = theme.bodyBg;
    viewerArea.style.backgroundColor = theme.bodyBg;

    if (rendition) {
      rendition.getContents().forEach(contents => {
        applyThemeStyles(contents);
      });
    }
  }

  async function saveReadingProgress(location, progress) {
    if (!currentBook) return;
    try {
      await fetch(`/api/books/${currentBook.id}/progress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          progress: progress,
          last_location: String(location)
        })
      });
    } catch (e) {
      console.warn('Failed to update progress', e);
    }
  }

  let controlsBound = false;
  function setupControls() {
    if (controlsBound) return;
    controlsBound = true;

    document.getElementById('epubPrevBtn').addEventListener('click', prevPage);
    document.getElementById('epubNextBtn').addEventListener('click', nextPage);
    document.getElementById('epubFontMinusBtn').addEventListener('click', () => changeFontSize(-10));
    document.getElementById('epubFontPlusBtn').addEventListener('click', () => changeFontSize(10));

    document.querySelectorAll('.epub-theme-btn').forEach(btn => {
      btn.addEventListener('click', () => setTheme(btn.dataset.theme));
    });

    document.getElementById('saveEpubChapterBtn').addEventListener('click', saveCurrentEpubChapter);

    // 切換純文字 vs HTML 模式
    toggleEditModeBtn.addEventListener('click', () => {
      isPlainTextMode = !isPlainTextMode;
      toggleEditModeBtn.innerText = isPlainTextMode ? '切換原始碼' : '切換純文字';
      updateEditorContent();
    });
  }

  return {
    loadEpub,
    goToLocation,
    nextPage,
    prevPage,
    highlightSelection,
    getCurrentLocation: () => {
      if (rendition && rendition.currentLocation() && rendition.currentLocation().start) {
        return rendition.currentLocation().start.cfi;
      }
      return '1';
    }
  };
})();
