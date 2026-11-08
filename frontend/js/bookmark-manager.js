// Acrobat 多重書籤管理器 (Multi-Bookmark System)

const BookmarkModule = (() => {
  let currentBookId = null;
  let bookmarks = [];
  let activeColorFilter = 'all';
  let searchQuery = '';
  let editingBookmarkId = null;
  let currentTags = [];

  // DOM 元素快取
  const container = document.getElementById('bookmarksListContainer');
  const modal = document.getElementById('bookmarkModal');
  const modalTitle = document.getElementById('bookmarkModalTitle');
  const modalLocationInfo = document.getElementById('bmModalLocationInfo');
  const inputTitle = document.getElementById('bmInputTitle');
  const selectCategory = document.getElementById('bmSelectCategory');
  const inputTag = document.getElementById('bmInputTag');
  const tagsBadgeContainer = document.getElementById('bmTagsBadgeContainer');
  const textQuote = document.getElementById('bmTextQuote');
  const textNote = document.getElementById('bmTextNote');
  const searchInput = document.getElementById('bmSearchInput');

  // 初始化多重書籤模組
  function init() {
    setupModalEvents();
    setupFilterEvents();
  }

  // 載入當前書籍之書籤
  async function loadBookmarks(bookId) {
    currentBookId = bookId;
    try {
      const res = await fetch(`/api/books/${bookId}/bookmarks`);
      bookmarks = await res.json();
      renderBookmarksList();
    } catch (err) {
      console.error('Failed to load bookmarks:', err);
    }
  }

  // 渲染側邊欄多重書籤卡片列表
  function renderBookmarksList() {
    container.innerHTML = '';

    const filtered = bookmarks.filter(bm => {
      const matchColor = activeColorFilter === 'all' || bm.color === activeColorFilter;
      const matchSearch = !searchQuery || 
        bm.title.toLowerCase().includes(searchQuery) ||
        (bm.note && bm.note.toLowerCase().includes(searchQuery)) ||
        (bm.quote && bm.quote.toLowerCase().includes(searchQuery)) ||
        (bm.tags && bm.tags.some(t => t.toLowerCase().includes(searchQuery)));
      return matchColor && matchSearch;
    });

    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="text-center py-8 text-slate-500">
          <i data-lucide="bookmark" class="w-8 h-8 mx-auto mb-2 opacity-40"></i>
          <p class="text-xs">尚無符合條件的書籤</p>
          <p class="text-[10px] mt-1 text-slate-600">按 Ctrl+B 或右上角「書籤」即可建立</p>
        </div>
      `;
      lucide.createIcons();
      return;
    }

    filtered.forEach(bm => {
      const card = document.createElement('div');
      card.className = `p-2.5 rounded-lg bg-[#1c1d1f] border border-[#33373a] hover:border-slate-500 transition group space-y-1 text-xs bm-badge-${bm.color}`;

      const tagsHtml = (bm.tags || []).map(t => 
        `<span class="bg-[#2a2d2e] text-slate-300 text-[10px] px-1.5 py-0.2 rounded">#${t}</span>`
      ).join(' ');

      card.innerHTML = `
        <div class="flex items-start justify-between gap-1">
          <div class="flex items-center gap-1.5 truncate">
            <span class="w-2.5 h-2.5 rounded-full bg-${getColorClass(bm.color)} shrink-0"></span>
            <span class="font-bold text-slate-200 truncate group-hover:text-amber-400 transition cursor-pointer" title="${bm.title}">
              ${bm.title}
            </span>
          </div>
          <span class="text-[10px] text-slate-400 shrink-0 font-mono bg-slate-800 px-1 py-0.2 rounded">P.${bm.location}</span>
        </div>

        <div class="text-[11px] text-slate-400 flex items-center gap-1">
          <span class="text-amber-400/90 font-medium">${bm.category || '核心'}</span>
          <div class="flex flex-wrap gap-1">${tagsHtml}</div>
        </div>

        ${bm.quote ? `
          <p class="text-[11px] text-slate-300 italic bg-[#242729] p-1.5 rounded border-l-2 border-slate-500 line-clamp-2" title="${bm.quote}">
            "${bm.quote}"
          </p>
        ` : ''}

        ${bm.note ? `
          <p class="text-[11px] text-amber-200/90 bg-amber-500/10 p-1.5 rounded line-clamp-2" title="${bm.note}">
            ${bm.note}
          </p>
        ` : ''}

        <div class="flex items-center justify-between pt-1 border-t border-[#2a2d2e] text-[10px] text-slate-500">
          <span>${formatDate(bm.created_at)}</span>
          <div class="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition">
            <button class="btn-jump text-emerald-400 hover:text-emerald-300 flex items-center gap-0.5" title="跳轉到此處">
              <i data-lucide="corner-down-right" class="w-3 h-3"></i> 跳轉
            </button>
            <button class="btn-edit text-slate-400 hover:text-white" title="編輯書籤">
              <i data-lucide="edit-2" class="w-3 h-3"></i>
            </button>
            <button class="btn-del text-red-400 hover:text-red-300" title="刪除書籤">
              <i data-lucide="trash-2" class="w-3 h-3"></i>
            </button>
          </div>
        </div>
      `;

      // 點擊卡片跳轉
      card.querySelector('.btn-jump').addEventListener('click', (e) => {
        e.stopPropagation();
        jumpToBookmark(bm);
      });
      card.addEventListener('dblclick', () => jumpToBookmark(bm));

      // 編輯書籤
      card.querySelector('.btn-edit').addEventListener('click', (e) => {
        e.stopPropagation();
        openEditBookmarkModal(bm);
      });

      // 刪除書籤
      card.querySelector('.btn-del').addEventListener('click', async (e) => {
        e.stopPropagation();
        if (confirm(`確定要刪除書籤「${bm.title}」嗎？`)) {
          await deleteBookmark(bm.id);
        }
      });

      container.appendChild(card);
    });

    lucide.createIcons();
  }

  // 取得色彩對應 CSS
  function getColorClass(c) {
    const map = {
      red: 'red-500',
      yellow: 'yellow-400',
      green: 'green-500',
      blue: 'blue-500',
      purple: 'purple-500'
    };
    return map[c] || 'red-500';
  }

  function formatDate(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  // 跳轉到書籤指定位置
  function jumpToBookmark(bm) {
    if (AppState.currentBook.file_type === 'pdf') {
      const page = parseInt(bm.location) || 1;
      PDFViewerModule.goToPage(page);
    } else {
      EPUBViewerModule.goToLocation(bm.location);
    }
  }

  // 開啟「新增多重書籤」彈窗 (支援外部傳入選取引文)
  function openAddBookmarkModal(customQuote = null) {
    editingBookmarkId = null;
    modalTitle.innerText = '新增多重書籤';
    
    // 自動取得當前位置
    let loc = '1';
    if (AppState.currentBook.file_type === 'pdf') {
      loc = String(PDFViewerModule.getCurrentPage());
      modalLocationInfo.innerText = `目前定位：第 ${loc} 頁`;
    } else {
      loc = String(EPUBViewerModule.getCurrentLocation());
      modalLocationInfo.innerText = `目前定位：EPUB 標籤 (${loc.substring(0, 15)}...)`;
    }

    inputTitle.value = `書籤 P.${loc}`;
    textQuote.value = (typeof customQuote === 'string' && customQuote.trim()) ? customQuote.trim() : (getSelectedText() || '');
    textNote.value = '';
    currentTags = ['重點'];
    renderModalTags();

    // 預設選中紅色
    document.querySelector('input[name="bmColor"][value="red"]').checked = true;
    modal.classList.remove('hidden');
    inputTitle.focus();
    inputTitle.select();
  }

  // 開啟「編輯多重書籤」彈窗
  function openEditBookmarkModal(bm) {
    editingBookmarkId = bm.id;
    modalTitle.innerText = '編輯多重書籤';
    modalLocationInfo.innerText = `目前定位：${bm.location}`;

    inputTitle.value = bm.title;
    selectCategory.value = bm.category || '重要核心';
    textQuote.value = bm.quote || '';
    textNote.value = bm.note || '';
    currentTags = [...(bm.tags || [])];
    renderModalTags();

    const colorRadio = document.querySelector(`input[name="bmColor"][value="${bm.color}"]`);
    if (colorRadio) colorRadio.checked = true;

    modal.classList.remove('hidden');
    inputTitle.focus();
  }

  // 取得滑鼠反白選取的文字
  function getSelectedText() {
    const sel = window.getSelection();
    return sel ? sel.toString().trim() : '';
  }

  // 渲染彈窗標籤徽章
  function renderModalTags() {
    tagsBadgeContainer.innerHTML = '';
    currentTags.forEach((tag, idx) => {
      const badge = document.createElement('span');
      badge.className = 'bg-slate-700 text-slate-200 text-xs px-2 py-0.5 rounded-full flex items-center gap-1';
      badge.innerHTML = `
        <span>#${tag}</span>
        <button class="hover:text-red-400 font-bold ml-1">&times;</button>
      `;
      badge.querySelector('button').addEventListener('click', () => {
        currentTags.splice(idx, 1);
        renderModalTags();
      });
      tagsBadgeContainer.appendChild(badge);
    });
  }

  // 儲存書籤 (新增或更新)
  async function saveBookmark() {
    const title = inputTitle.value.trim();
    if (!title) {
      alert('請輸入書籤標題');
      return;
    }

    const color = document.querySelector('input[name="bmColor"]:checked')?.value || 'red';
    const category = selectCategory.value;
    const quote = textQuote.value.trim();
    const note = textNote.value.trim();

    let location = '1';
    if (AppState.currentBook.file_type === 'pdf') {
      location = String(PDFViewerModule.getCurrentPage());
    } else {
      location = String(EPUBViewerModule.getCurrentLocation());
    }

    try {
      if (editingBookmarkId) {
        // 更新
        await fetch(`/api/books/${currentBookId}/bookmarks/${editingBookmarkId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title, category, color, tags: currentTags, quote, note
          })
        });
      } else {
        // 新增
        await fetch(`/api/books/${currentBookId}/bookmarks`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            location, title, category, color, tags: currentTags, quote, note
          })
        });
      }

      modal.classList.add('hidden');
      await loadBookmarks(currentBookId);
    } catch (err) {
      console.error('Failed to save bookmark:', err);
      alert('儲存書籤失敗');
    }
  }

  // 刪除書籤
  async function deleteBookmark(bookmarkId) {
    try {
      await fetch(`/api/books/${currentBookId}/bookmarks/${bookmarkId}`, {
        method: 'DELETE'
      });
      await loadBookmarks(currentBookId);
    } catch (err) {
      console.error('Failed to delete bookmark:', err);
    }
  }

  // 匯出當前書籍書籤為 Markdown
  function exportMarkdown() {
    if (!currentBookId) return;
    window.open(`/api/bookmarks/export-markdown/${currentBookId}`, '_blank');
  }

  // 彈窗事件綁定
  function setupModalEvents() {
    document.getElementById('quickAddBookmarkBtn').addEventListener('click', openAddBookmarkModal);
    document.getElementById('btnSidebarAddBookmark').addEventListener('click', openAddBookmarkModal);
    document.getElementById('closeBookmarkModalBtn').addEventListener('click', () => modal.classList.add('hidden'));
    document.getElementById('cancelBookmarkModalBtn').addEventListener('click', () => modal.classList.add('hidden'));
    document.getElementById('saveBookmarkModalBtn').addEventListener('click', saveBookmark);
    document.getElementById('exportMarkdownNotesBtn').addEventListener('click', exportMarkdown);

    // 標籤輸入框按 Enter 加入
    inputTag.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const val = inputTag.value.trim().replace(/^#/, '');
        if (val && !currentTags.includes(val)) {
          currentTags.push(val);
          renderModalTags();
          inputTag.value = '';
        }
      }
    });

    // 快捷鍵 Ctrl + B 快速開啟書籤
    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        if (AppState.currentBook && !modal.classList.contains('hidden')) {
          modal.classList.add('hidden');
        } else if (AppState.currentBook) {
          openAddBookmarkModal();
        }
      }
    });
  }

  // 篩選事件綁定
  function setupFilterEvents() {
    // 依色彩篩選
    document.querySelectorAll('.filter-bm-color').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-bm-color').forEach(b => b.classList.remove('active', 'ring-2', 'ring-white'));
        btn.classList.add('active', 'ring-2', 'ring-white');
        activeColorFilter = btn.dataset.color;
        renderBookmarksList();
      });
    });

    // 搜尋書籤
    searchInput.addEventListener('input', (e) => {
      searchQuery = e.target.value.trim().toLowerCase();
      renderBookmarksList();
    });
  }

  // 立即初始化
  init();

  return {
    loadBookmarks,
    openAddBookmarkModal,
    exportMarkdown
  };
})();

