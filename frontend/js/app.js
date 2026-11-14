// Acrobat Bookshelf - 主應用程式控制邏輯

const AppState = {
  currentBook: null,
  books: [],
  filterType: 'all',
  searchQuery: '',
  activeSidebarTab: 'panelBookmarks'
};

// DOM 元素快取
const dom = {
  bookshelfView: document.getElementById('bookshelfView'),
  readerView: document.getElementById('readerView'),
  booksGrid: document.getElementById('booksGrid'),
  emptyShelfPrompt: document.getElementById('emptyShelfPrompt'),
  searchInput: document.getElementById('searchInput'),
  bookUploadInput: document.getElementById('bookUploadInput'),
  dropZoneNotice: document.getElementById('dropZoneNotice'),
  statTotalBooks: document.getElementById('statTotalBooks'),
  statPdfBooks: document.getElementById('statPdfBooks'),
  statEpubBooks: document.getElementById('statEpubBooks'),
  statTotalBookmarks: document.getElementById('statTotalBookmarks'),
  booksCountBadge: document.getElementById('booksCountBadge'),
  backToBookshelfBtn: document.getElementById('backToBookshelfBtn'),
  readerDocBadge: document.getElementById('readerDocBadge'),
  readerDocTitle: document.getElementById('readerDocTitle'),
  toggleSidebarBtn: document.getElementById('toggleSidebarBtn'),
  acrobatSidebar: document.getElementById('acrobatSidebar'),
  openGlobalBookmarksBtn: document.getElementById('openGlobalBookmarksBtn'),
  globalBookmarksDrawer: document.getElementById('globalBookmarksDrawer'),
  closeGlobalBookmarksBtn: document.getElementById('closeGlobalBookmarksBtn'),
  globalBookmarksContainer: document.getElementById('globalBookmarksContainer'),
  readerDeleteBookBtn: document.getElementById('readerDeleteBookBtn'),
  readerConvertToTwBtn: document.getElementById('readerConvertToTwBtn')
};

// 初始化載入
document.addEventListener('DOMContentLoaded', async () => {
  setupEventListeners();
  // 嚴防瀏覽器密碼管理器/Autofill 誤將 Email 填入書櫃搜尋欄
  if (dom.searchInput && (dom.searchInput.value.includes('@') || !dom.searchInput.dataset.userTyped)) {
    dom.searchInput.value = '';
    AppState.searchQuery = '';
  }
  await fetchBooks();
  setupDragAndDrop();
});

// 事件監聽設置
function setupEventListeners() {
  // 搜尋過濾
  const clearSearchBtn = document.getElementById('clearSearchInputBtn');
  const updateClearBtn = () => {
    if (clearSearchBtn) {
      if (dom.searchInput.value.trim().length > 0) {
        clearSearchBtn.classList.remove('hidden');
      } else {
        clearSearchBtn.classList.add('hidden');
      }
    }
  };

  dom.searchInput.addEventListener('input', (e) => {
    // 標記為使用者主動打字，防止被誤判為 autofill
    dom.searchInput.dataset.userTyped = 'true';
    AppState.searchQuery = e.target.value.trim().toLowerCase();
    updateClearBtn();
    renderBooksGrid();
  });

  if (clearSearchBtn) {
    clearSearchBtn.addEventListener('click', () => {
      dom.searchInput.value = '';
      delete dom.searchInput.dataset.userTyped;
      AppState.searchQuery = '';
      updateClearBtn();
      renderBooksGrid();
      dom.searchInput.focus();
    });
  }

  // 格式篩選按鈕 (全部 / PDF / EPUB)
  document.querySelectorAll('.filter-type-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-type-btn').forEach(b => b.classList.remove('active', 'bg-red-600', 'text-white'));
      btn.classList.add('active', 'bg-red-600', 'text-white');
      AppState.filterType = btn.dataset.type;
      renderBooksGrid();
    });
  });

  // 上傳書籍檔案
  dom.bookUploadInput.addEventListener('change', async (e) => {
    const files = e.target.files;
    if (files.length > 0) {
      await uploadFiles(files);
      dom.bookUploadInput.value = '';
    }
  });

  // 返回書櫃視圖
  dom.backToBookshelfBtn.addEventListener('click', () => {
    if (window.hideSelectionQuickBar) window.hideSelectionQuickBar();
    switchView('bookshelf');
  });

  // 閱讀器內部刪除書籍
  dom.readerDeleteBookBtn.addEventListener('click', async () => {
    if (!AppState.currentBook) return;
    await confirmAndDeleteBook(AppState.currentBook.id, AppState.currentBook.title, true);
  });

  // 閱讀器內部 EPUB 一鍵轉繁體
  if (dom.readerConvertToTwBtn) {
    dom.readerConvertToTwBtn.addEventListener('click', async () => {
      if (!AppState.currentBook || AppState.currentBook.file_type !== 'epub') return;
      await convertBookToTraditional(AppState.currentBook.id, AppState.currentBook.title, true);
    });
  }

  // 收合 / 展開側邊欄
  dom.toggleSidebarBtn.addEventListener('click', () => {
    dom.acrobatSidebar.classList.toggle('hidden');
    dom.toggleSidebarBtn.classList.toggle('active');
    window.dispatchEvent(new Event('resize'));
  });

  // 側邊欄頁籤切換
  document.querySelectorAll('.sidebar-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.sidebar-tab-btn').forEach(b => {
        b.classList.remove('active', 'text-slate-300', 'border-red-500');
        b.classList.add('text-slate-400', 'border-transparent');
      });
      btn.classList.add('active', 'text-slate-300', 'border-red-500');
      btn.classList.remove('text-slate-400', 'border-transparent');

      const targetPanel = btn.dataset.panel;
      document.querySelectorAll('.sidebar-panel').forEach(p => p.classList.add('hidden'));
      const activeP = document.getElementById(targetPanel);
      if (activeP) activeP.classList.remove('hidden');
      AppState.activeSidebarTab = targetPanel;
    });
  });

  // 全域書籤總覽抽屜
  dom.openGlobalBookmarksBtn.addEventListener('click', openGlobalBookmarksDrawer);
  dom.closeGlobalBookmarksBtn.addEventListener('click', () => {
    dom.globalBookmarksDrawer.classList.add('hidden');
  });

  // 註冊外層視窗的全域鍵盤與滑鼠滾輪翻頁監聽
  window.addEventListener('keydown', handleGlobalPagingKey);
  window.addEventListener('wheel', handleGlobalWheelPaging, { passive: false });
}

// 全域翻頁時間戳防抖
let lastGlobalPagingTimestamp = 0;

// 全域統一鍵盤翻頁處理器 (供主視窗與 EPUB iframe 內部共同調用)
function handleGlobalPagingKey(e) {
  // 處於書櫃視圖時不翻頁
  if (!dom.bookshelfView.classList.contains('hidden') || !AppState.currentBook) return;

  // 使用者正在輸入框、文字區塊中打字時不翻頁
  const tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : '';
  if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return;

  // 書籤 Modal 或便籤視窗開啟時不觸發翻頁
  const bmModal = document.getElementById('bookmarkModal');
  const noteBox = document.getElementById('floatingNoteBox');
  if (bmModal && !bmModal.classList.contains('hidden')) return;
  if (noteBox && !noteBox.classList.contains('hidden')) return;

  const key = e.key;
  const isShift = e.shiftKey;

  // 下一頁條件: 右方向鍵、下方向鍵、PageDown、空白鍵 (無 Shift)
  const isNext = key === 'ArrowRight' || key === 'ArrowDown' || key === 'PageDown' || (e.code === 'Space' && !isShift);

  // 上一頁條件: 左方向鍵、上方向鍵、PageUp、Shift+空白鍵
  const isPrev = key === 'ArrowLeft' || key === 'ArrowUp' || key === 'PageUp' || (e.code === 'Space' && isShift);

  if (!isNext && !isPrev) return;

  e.preventDefault();
  if (typeof e.stopPropagation === 'function') e.stopPropagation();

  // 嚴防同一按鍵事件在 iframe 與主視窗間雙重分發
  if (e._handledByBookshelf) return;
  e._handledByBookshelf = true;

  // 1. 嚴格過濾作業系統長按按鍵產生的重複事件 (Key Repeat)
  if (e.repeat) return;

  // 2. 嚴格時間戳防抖節流 (延長至 300ms 內禁止連擊，徹底阻擋雙重事件傳播與連翻)
  const now = Date.now();
  if (now - lastGlobalPagingTimestamp < 300) return;
  lastGlobalPagingTimestamp = now;

  if (window.hideSelectionQuickBar) window.hideSelectionQuickBar();

  if (isNext) {
    if (AppState.currentBook.file_type === 'pdf') {
      PDFViewerModule.nextPage();
    } else {
      EPUBViewerModule.nextPage();
    }
  } else if (isPrev) {
    if (AppState.currentBook.file_type === 'pdf') {
      PDFViewerModule.prevPage();
    } else {
      EPUBViewerModule.prevPage();
    }
  }
}

// 暴露到 window 供 iframe 內容調用
window.handleGlobalPagingKey = handleGlobalPagingKey;

// 全域滑鼠滾輪翻頁時間戳防抖
let lastGlobalWheelTimestamp = 0;

// 全域統一滑鼠滾輪翻頁處理器 (供主視窗與 EPUB iframe 內部共同調用)
function handleGlobalWheelPaging(e) {
  // 1. 處於書櫃清單視圖，或未載入任何書籍，不攔截滾輪（保持書櫃正常滾動）
  if (!dom.bookshelfView.classList.contains('hidden') || !AppState.currentBook) return;

  // 2. 若使用者按住 Ctrl 或 Meta 鍵滾動，保留標準縮放功能
  if (e.ctrlKey || e.metaKey) return;

  // 3. 嚴防同一滾輪事件在 iframe 與外層視窗重複觸發
  if (e._handledByBookshelfWheel) return;

  // 4. 檢查滾輪目標是否位於特定的獨立可滾動面板內（如書籤清單、筆記列表、章節編輯輸入框等）
  const target = e.target;
  if (target && typeof target.closest === 'function') {
    const scrollableModal = target.closest('#bookmarkModal, #floatingNoteBox, #epubChapterContentArea, #sidebarOutline, #sidebarThumbnails, .overflow-y-auto, .overflow-auto');
    if (scrollableModal) {
      // 在可滾動面板內部時，允許正常滾動面板內容
      return;
    }
  }

  // 5. 判斷垂直滾動幅度 (忽略微小手震或微晃動)
  if (Math.abs(e.deltaY) < 18) return;

  // 標記為已被書櫃滾輪處理器接管
  e._handledByBookshelfWheel = true;

  // 6. 阻斷預設行為（防止引發外層頁面或容器的預設位移破壞排版）
  if (e.cancelable) {
    e.preventDefault();
  }
  if (typeof e.stopPropagation === 'function') {
    e.stopPropagation();
  }

  // 7. 防暴衝防抖機制 (Cool-down 節流 280ms，杜絕實體滾輪單次滾動發出多個事件導致連翻)
  const now = Date.now();
  if (now - lastGlobalWheelTimestamp < 280) {
    return;
  }
  lastGlobalWheelTimestamp = now;

  if (window.hideSelectionQuickBar) window.hideSelectionQuickBar();

  // 8. 滾輪向下滾動 (deltaY > 0) -> 下一頁
  //    滾輪向上滾動 (deltaY < 0) -> 上一頁
  if (e.deltaY > 0) {
    if (AppState.currentBook.file_type === 'pdf') {
      PDFViewerModule.nextPage();
    } else {
      EPUBViewerModule.nextPage();
    }
  } else if (e.deltaY < 0) {
    if (AppState.currentBook.file_type === 'pdf') {
      PDFViewerModule.prevPage();
    } else {
      EPUBViewerModule.prevPage();
    }
  }
}

// 暴露到 window 供 iframe 內容調用
window.handleGlobalWheelPaging = handleGlobalWheelPaging;

// 取得書籍列表
async function fetchBooks() {
  try {
    const res = await fetch('/api/books');
    AppState.books = await res.json();
    updateStatistics();
    renderBooksGrid();
  } catch (err) {
    console.error('Failed to load books:', err);
  }
}

// 更新書櫃統計數字
function updateStatistics() {
  const total = AppState.books.length;
  const pdfCount = AppState.books.filter(b => b.file_type === 'pdf').length;
  const epubCount = AppState.books.filter(b => b.file_type === 'epub').length;
  const totalBm = AppState.books.reduce((acc, b) => acc + (b.bookmarks_count || 0), 0);

  dom.statTotalBooks.innerText = `${total} 本`;
  dom.statPdfBooks.innerText = `${pdfCount} 本`;
  dom.statEpubBooks.innerText = `${epubCount} 本`;
  dom.statTotalBookmarks.innerText = `${totalBm} 則`;
  dom.booksCountBadge.innerText = `共 ${total} 本`;
}

// HTML 跳脫輔助防護
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// 渲染書籍網格
function renderBooksGrid() {
  dom.booksGrid.innerHTML = '';
  
  const query = (AppState.searchQuery || '').trim().toLowerCase();
  const filtered = AppState.books.filter(book => {
    const title = (book.title || '').toLowerCase();
    const author = (book.author || '').toLowerCase();
    const matchType = AppState.filterType === 'all' || (book.file_type && book.file_type.toLowerCase() === AppState.filterType);
    const matchSearch = !query || title.includes(query) || author.includes(query);
    return matchType && matchSearch;
  });

  if (filtered.length === 0) {
    if (query || AppState.filterType !== 'all') {
      dom.emptyShelfPrompt.classList.add('hidden');
      dom.booksGrid.innerHTML = `
        <div class="col-span-full py-16 text-center text-slate-400">
          <i data-lucide="search-x" class="w-12 h-12 mx-auto mb-3 text-slate-500"></i>
          <p class="text-base font-semibold text-slate-200">找不到符合條件的書籍</p>
          <p class="text-xs text-slate-400 mt-1">
            目前關鍵字：<span class="text-red-400 font-mono font-bold">${escapeHtml(query || '無')}</span>
            ${AppState.filterType !== 'all' ? `，格式：<span class="text-red-400 font-bold">${AppState.filterType.toUpperCase()}</span>` : ''}
          </p>
          <button id="resetSearchFilterBtn" class="mt-4 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-xs font-medium transition inline-flex items-center gap-1.5 shadow">
            <i data-lucide="rotate-ccw" class="w-3.5 h-3.5"></i> 清除搜尋篩選，顯示所有書籍
          </button>
        </div>
      `;
      const resetBtn = document.getElementById('resetSearchFilterBtn');
      if (resetBtn) {
        resetBtn.onclick = () => {
          AppState.searchQuery = '';
          AppState.filterType = 'all';
          if (dom.searchInput) dom.searchInput.value = '';
          document.querySelectorAll('.filter-type-btn').forEach(b => {
            if (b.dataset.type === 'all') b.classList.add('active', 'bg-red-600', 'text-white');
            else b.classList.remove('active', 'bg-red-600', 'text-white');
          });
          renderBooksGrid();
        };
      }
      if (window.lucide) lucide.createIcons();
      return;
    }
    dom.emptyShelfPrompt.classList.remove('hidden');
    return;
  }
  dom.emptyShelfPrompt.classList.add('hidden');

  filtered.forEach(book => {
    const card = document.createElement('div');
    card.className = 'book-card group cursor-pointer flex flex-col bg-slate-800/80 hover:bg-slate-800 border border-slate-700/60 hover:border-red-500/50 rounded-xl p-3 transition duration-200 shadow-md relative';
    
    const isPdf = book.file_type === 'pdf';
    const badgeColor = isPdf ? 'bg-red-600' : 'bg-emerald-600';
    const progress = Math.round(book.current_progress || 0);
    const safeTitle = escapeHtml(book.title || '未命名書籍');
    const safeAuthor = escapeHtml(book.author || '未知作者');

    card.innerHTML = `
      <div class="book-cover-container w-full aspect-[1/1.4] bg-slate-900 rounded-lg overflow-hidden relative mb-3">
        <img src="${book.cover_image}" alt="${safeTitle}" class="w-full h-full object-cover group-hover:scale-105 transition duration-300"
             onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'200\\' height=\\'280\\' viewBox=\\'0 0 200 280\\'><rect width=\\'200\\' height=\\'280\\' fill=\\'%23334155\\'/><text x=\\'50%\\' y=\\'50%\\' fill=\\'%2394a3b8\\' font-size=\\'14\\' text-anchor=\\'middle\\'>封面載入中</text></svg>';">
        
        <div class="absolute top-2 left-2 ${badgeColor} text-[10px] font-bold text-white px-2 py-0.5 rounded shadow uppercase z-10">
          ${escapeHtml(book.file_type)}
        </div>

        <!-- 卡片右上角快捷操作區 -->
        <div class="absolute top-2 right-2 flex items-center gap-1 z-20">
          ${!isPdf ? `
          <button class="convert-tw-btn bg-slate-900/80 hover:bg-emerald-600 text-slate-300 hover:text-white px-1.5 py-1 rounded-md transition shadow-md opacity-0 group-hover:opacity-100 text-[10px] font-bold" 
                  title="一鍵將此 EPUB 轉為台灣繁體中文" data-id="${book.id}" data-title="${safeTitle}">
            繁
          </button>
          ` : ''}

          <!-- 刪除書籍按鈕 (垃圾桶) -->
          <button class="delete-book-btn bg-slate-900/80 hover:bg-red-600 text-slate-300 hover:text-white p-1.5 rounded-md transition shadow-md opacity-0 group-hover:opacity-100" 
                  title="刪除此書" data-id="${book.id}" data-title="${safeTitle}">
            <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
          </button>
        </div>

        ${book.bookmarks_count > 0 ? `
          <div class="absolute bottom-2 right-2 bg-amber-500/90 text-slate-900 text-[10px] font-extrabold px-1.5 py-0.5 rounded flex items-center gap-0.5 shadow z-10">
            <i data-lucide="bookmark" class="w-3 h-3 fill-slate-900"></i> ${book.bookmarks_count}
          </div>
        ` : ''}

        <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition flex items-center justify-center backdrop-blur-[2px]">
          <span class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs font-semibold shadow-lg flex items-center gap-1.5">
            <i data-lucide="book-open" class="w-4 h-4"></i> 開啟閱讀
          </span>
        </div>
      </div>

      <div class="flex-1 flex flex-col justify-between">
        <div>
          <h3 class="font-bold text-sm text-slate-100 line-clamp-2 leading-snug group-hover:text-red-400 transition" title="${safeTitle}">
            ${safeTitle}
          </h3>
          <p class="text-xs text-slate-400 truncate mt-1">${safeAuthor}</p>
        </div>

        <div class="mt-3 pt-2 border-t border-slate-700/60">
          <div class="flex items-center justify-between text-[11px] text-slate-400 mb-1">
            <span>閱讀進度</span>
            <span class="font-mono text-slate-300 font-medium">${progress}%</span>
          </div>
          <div class="w-full bg-slate-700 rounded-full h-1.5 overflow-hidden">
            <div class="bg-red-500 h-1.5 rounded-full" style="width: ${progress}%"></div>
          </div>
        </div>
      </div>
    `;

    // 點擊卡片開啟書籍 (若點擊的是刪除或轉繁體按鈕則忽略)
    card.addEventListener('click', (e) => {
      if (e.target.closest('.delete-book-btn') || e.target.closest('.convert-tw-btn')) return;
      openBook(book.id);
    });

    // 綁定轉繁體按鈕 (EPUB 專屬)
    const convBtn = card.querySelector('.convert-tw-btn');
    if (convBtn) {
      convBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        await convertBookToTraditional(book.id, book.title, false);
      });
    }

    // 綁定刪除按鈕
    const delBtn = card.querySelector('.delete-book-btn');
    delBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      await confirmAndDeleteBook(book.id, book.title, false);
    });

    dom.booksGrid.appendChild(card);
  });

  lucide.createIcons();
}

// 繁體轉換共用函式
async function convertBookToTraditional(bookId, bookTitle, reloadIfOpen = false) {
  const confirmed = confirm(`確定要將《${bookTitle}》全量轉換為台灣繁體中文嗎？\n（系統將自動轉換所有章節內文與標題，並保留完整排版與圖片）`);
  if (!confirmed) return;

  try {
    const res = await fetch(`/api/books/${bookId}/convert-to-traditional`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '轉換失敗');

    alert(data.message || `《${bookTitle}》已成功轉換為繁體中文！`);

    if (reloadIfOpen && AppState.currentBook && AppState.currentBook.id === bookId) {
      await openBook(bookId);
    } else {
      await fetchBooks();
    }
  } catch (err) {
    console.error('Failed to convert EPUB to traditional:', err);
    alert('轉換失敗：' + (err.message || '請確認後端連線'));
  }
}

// 刪除書籍共用函式
async function confirmAndDeleteBook(bookId, bookTitle, isCurrentlyOpen = false) {
  const confirmed = confirm(`確定要從書櫃中刪除《${bookTitle}》嗎？\n（此操作將清除此書的檔案、書籤與所有註解）`);
  if (!confirmed) return;

  try {
    const res = await fetch(`/api/books/${bookId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Delete failed');

    alert(`書籍《${bookTitle}》已成功從書櫃刪除！`);

    if (isCurrentlyOpen) {
      switchView('bookshelf');
    }
    await fetchBooks();
  } catch (err) {
    console.error('Failed to delete book:', err);
    alert('刪除失敗，請檢查檔案權限或後端連線');
  }
}

// 開啟書籍
async function openBook(bookId) {
  try {
    const res = await fetch(`/api/books/${bookId}`);
    const book = await res.json();
    AppState.currentBook = book;

    dom.readerDocBadge.innerText = book.file_type.toUpperCase();
    dom.readerDocBadge.className = book.file_type === 'pdf' ? 
      'px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-600 text-white uppercase' :
      'px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-600 text-white uppercase';
    dom.readerDocTitle.innerText = book.title;

    switchView('reader');

    // 依格式調度對應閱讀器
    if (book.file_type === 'pdf') {
      if (dom.readerConvertToTwBtn) dom.readerConvertToTwBtn.classList.add('hidden');
      document.getElementById('epubEditTabBtn').classList.add('hidden');
      document.getElementById('sidebarThumbTabBtn').classList.remove('hidden');
      await PDFViewerModule.loadPdf(book);
    } else {
      if (dom.readerConvertToTwBtn) dom.readerConvertToTwBtn.classList.remove('hidden');
      document.getElementById('epubEditTabBtn').classList.remove('hidden');
      document.getElementById('sidebarThumbTabBtn').classList.add('hidden');
      await EPUBViewerModule.loadEpub(book);
    }

    // 載入多重書籤
    await BookmarkModule.loadBookmarks(book.id);
    // 載入註解
    await AnnotationModule.loadAnnotations(book.id);

  } catch (err) {
    console.error('Error opening book:', err);
    alert('開啟書籍時發生錯誤，請檢查檔案是否存在');
  }
}

// 切換視圖 (bookshelf <-> reader)
function switchView(view) {
  const crawlerView = document.getElementById('crawlerView');
  const updatesView = document.getElementById('updatesView');
  const mainAppHeader = document.getElementById('mainAppHeader');
  const searchGroup = document.getElementById('bookshelfSearchGroup');
  const navBookshelfBtn = document.getElementById('navBookshelfBtn');
  const navCrawlerBtn = document.getElementById('navCrawlerBtn');
  const navUpdatesBtn = document.getElementById('navUpdatesBtn');

  if (crawlerView) crawlerView.classList.add('hidden');
  if (updatesView) updatesView.classList.add('hidden');

  if (view === 'bookshelf') {
    if (mainAppHeader) mainAppHeader.classList.remove('hidden');
    if (searchGroup) searchGroup.classList.remove('invisible');

    // 嚴防切換回書櫃時受瀏覽器 Autofill 污染
    if (dom.searchInput && (dom.searchInput.value.includes('@') || !dom.searchInput.dataset.userTyped)) {
      dom.searchInput.value = '';
      AppState.searchQuery = '';
      const clearBtn = document.getElementById('clearSearchInputBtn');
      if (clearBtn) clearBtn.classList.add('hidden');
    }
    
    // 更新導覽列高亮
    if (navBookshelfBtn) {
      navBookshelfBtn.classList.add('bg-red-600', 'text-white', 'shadow-md');
      navBookshelfBtn.classList.remove('text-slate-300', 'hover:bg-slate-700');
    }
    if (navCrawlerBtn) {
      navCrawlerBtn.classList.remove('bg-red-600', 'text-white', 'shadow-md');
      navCrawlerBtn.classList.add('text-slate-300', 'hover:bg-slate-700');
    }
    if (navUpdatesBtn) {
      navUpdatesBtn.classList.remove('bg-red-600', 'text-white', 'shadow-md');
      navUpdatesBtn.classList.add('text-slate-300', 'hover:bg-slate-700');
    }

    dom.bookshelfView.classList.remove('hidden');
    dom.readerView.classList.add('hidden');
    fetchBooks(); // 返回時刷新進度
  } else {
    // 進入閱讀模式，隱藏全域 Header，由閱讀器頂部工具列接管
    if (mainAppHeader) mainAppHeader.classList.add('hidden');
    dom.bookshelfView.classList.add('hidden');
    dom.readerView.classList.remove('hidden');
  }
  lucide.createIcons();
}

// 檔案拖曳上傳支援
function setupDragAndDrop() {
  const dropZone = window;

  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dom.dropZoneNotice.classList.remove('hidden');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dom.dropZoneNotice.classList.add('hidden');
    });
  });

  dropZone.addEventListener('drop', async (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      await uploadFiles(files);
    }
  });
}

// 上傳檔案處理 (具備防重複上傳鎖)
let isUploading = false;
async function uploadFiles(files) {
  if (isUploading) return;
  isUploading = true;
  
  try {
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const ext = file.name.split('.').pop().toLowerCase();
      if (!['pdf', 'epub'].includes(ext)) {
        alert(`不支援的檔案格式：${file.name}，僅支援 PDF 與 EPUB`);
        continue;
      }

      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch('/api/books/upload', {
          method: 'POST',
          body: formData
        });
        if (!res.ok) throw new Error('Upload failed');
      } catch (err) {
        console.error('Failed to upload file:', err);
        alert(`上傳 ${file.name} 失敗`);
      }
    }
    await fetchBooks();
  } finally {
    isUploading = false;
  }
}

// 全域跨書多重書籤檢索抽屜
async function openGlobalBookmarksDrawer() {
  dom.globalBookmarksContainer.innerHTML = '<div class="text-center py-6 text-slate-500">載入所有書籤中...</div>';
  dom.globalBookmarksDrawer.classList.remove('hidden');

  try {
    let allBm = [];
    for (const book of AppState.books) {
      const res = await fetch(`/api/books/${book.id}/bookmarks`);
      const bms = await res.json();
      bms.forEach(bm => {
        bm.bookTitle = book.title;
        bm.fileType = book.file_type;
        allBm.push(bm);
      });
    }

    if (allBm.length === 0) {
      dom.globalBookmarksContainer.innerHTML = '<div class="text-center py-10 text-slate-500">尚無任何書籤。您可以在閱讀器中隨時按 Ctrl+B 加入！</div>';
      return;
    }

    dom.globalBookmarksContainer.innerHTML = '';
    allBm.forEach(bm => {
      const card = document.createElement('div');
      card.className = `p-3 rounded-lg bg-[#1c1d1f] border border-slate-700 hover:border-amber-500/50 cursor-pointer transition space-y-1.5 bm-badge-${bm.color}`;
      
      const tagsHtml = (bm.tags || []).map(t => `<span class="bg-slate-700 text-slate-300 text-[10px] px-1.5 py-0.5 rounded">#${t}</span>`).join(' ');

      card.innerHTML = `
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold text-white">${bm.title}</span>
          <span class="text-[10px] text-slate-400">位址: ${bm.location}</span>
        </div>
        <div class="text-[11px] text-slate-400 flex items-center gap-1.5">
          <i data-lucide="book" class="w-3 h-3 text-red-400"></i>
          <span class="truncate">${bm.bookTitle}</span>
        </div>
        ${bm.quote ? `<p class="text-[11px] text-slate-300 italic border-l-2 border-slate-500 pl-2 py-0.5">"${bm.quote}"</p>` : ''}
        ${bm.note ? `<p class="text-[11px] text-amber-200/90 bg-amber-500/10 p-1.5 rounded">${bm.note}</p>` : ''}
        <div class="flex items-center gap-1 pt-1">
          <span class="text-[10px] font-medium text-slate-400">${bm.category || ''}</span>
          ${tagsHtml}
        </div>
      `;

      card.addEventListener('click', async () => {
        dom.globalBookmarksDrawer.classList.add('hidden');
        await openBook(bm.book_id);
        // 跳轉到位置
        if (bm.fileType === 'pdf') {
          PDFViewerModule.goToPage(parseInt(bm.location) || 1);
        } else {
          EPUBViewerModule.goToLocation(bm.location);
        }
      });

      dom.globalBookmarksContainer.appendChild(card);
    });

    lucide.createIcons();
  } catch (err) {
    console.error('Error fetching global bookmarks:', err);
  }
}

// 暴露全域函數
window.openBookById = openBook;
window.fetchBooks = fetchBooks;
window.AppState = AppState;
window.renderBooksGrid = renderBooksGrid;
