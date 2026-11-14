// Acrobat Bookshelf - 小說抓取與自動追更前端邏輯模組 (crawler.js)

const CrawlerModule = (() => {
  let supportedSites = [];
  let currentSite = 'biquge';
  let supportedCategories = [];
  let currentCategory = 'all';
  let activeTaskId = null;
  let taskPollTimer = null;
  let trackedBooks = [];
  let updateCheckResults = {}; // book_key -> result

  // 初始化模組
  async function init() {
    setupDomListeners();
    await Promise.all([loadSupportedSites(), loadSupportedCategories()]);
    // 預設先背景載入小說網站官方排行榜前幾名小說
    loadExploreNovels(currentSite, currentCategory);
  }

  // 設置 DOM 事件監聽
  function setupDomListeners() {
    // 導覽標籤切換按鈕
    const navBookshelfBtn = document.getElementById('navBookshelfBtn');
    const navCrawlerBtn = document.getElementById('navCrawlerBtn');
    const navUpdatesBtn = document.getElementById('navUpdatesBtn');

    if (navBookshelfBtn) {
      navBookshelfBtn.addEventListener('click', () => switchMainTab('bookshelf'));
    }
    if (navCrawlerBtn) {
      navCrawlerBtn.addEventListener('click', () => {
        switchMainTab('crawler');
        if (!document.getElementById('crawlerBooksGrid').hasChildNodes()) {
          loadExploreNovels(currentSite, currentCategory);
        }
      });
    }
    if (navUpdatesBtn) {
      navUpdatesBtn.addEventListener('click', () => {
        switchMainTab('updates');
        loadTrackedNovels();
      });
    }

    // 小說搜尋與網址解析
    const crawlerSearchBtn = document.getElementById('crawlerSearchBtn');
    const crawlerSearchInput = document.getElementById('crawlerSearchInput');
    if (crawlerSearchBtn && crawlerSearchInput) {
      crawlerSearchBtn.addEventListener('click', () => handleSearch());
      crawlerSearchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleSearch();
      });
    }

    // 詳情彈窗關閉按鈕
    const closeDetailModalBtn = document.getElementById('closeDetailModalBtn');
    const crawlerDetailModal = document.getElementById('crawlerDetailModal');
    if (closeDetailModalBtn && crawlerDetailModal) {
      closeDetailModalBtn.addEventListener('click', () => {
        crawlerDetailModal.classList.add('hidden');
      });
      crawlerDetailModal.addEventListener('click', (e) => {
        if (e.target === crawlerDetailModal) {
          crawlerDetailModal.classList.add('hidden');
        }
      });
    }

    // 一鍵檢查全部更新
    const checkAllUpdatesBtn = document.getElementById('checkAllUpdatesBtn');
    if (checkAllUpdatesBtn) {
      checkAllUpdatesBtn.addEventListener('click', () => handleCheckAllUpdates());
    }

    // 同步書庫按鈕
    const syncBookshelfBtn = document.getElementById('syncBookshelfBtn');
    if (syncBookshelfBtn) {
      syncBookshelfBtn.addEventListener('click', () => handleSyncBookshelf());
    }

    // 關閉下載進度浮動小視窗按鈕
    const closeFloatingProgressBtn = document.getElementById('closeFloatingProgressBtn');
    if (closeFloatingProgressBtn) {
      closeFloatingProgressBtn.addEventListener('click', () => {
        const bar = document.getElementById('crawlerFloatingProgress');
        if (bar) bar.classList.add('hidden');
      });
    }

    // 全域 ESC 快捷鍵關閉彈窗與浮動小視窗
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const modal = document.getElementById('crawlerDetailModal');
        if (modal && !modal.classList.contains('hidden')) {
          modal.classList.add('hidden');
        }
        const bar = document.getElementById('crawlerFloatingProgress');
        if (bar && !bar.classList.contains('hidden')) {
          bar.classList.add('hidden');
        }
      }
    });

    // 搜尋更新列表
    const updateSearchInput = document.getElementById('updateSearchInput');
    if (updateSearchInput) {
      updateSearchInput.addEventListener('input', (e) => {
        renderTrackedBooksList(e.target.value.trim().toLowerCase());
      });
    }

    // Z-Library 設定彈窗控制
    const openZlibConfigBtn = document.getElementById('openZlibConfigBtn');
    const zlibConfigModal = document.getElementById('zlibConfigModal');
    const closeZlibModalBtn = document.getElementById('closeZlibModalBtn');
    const cancelZlibModalBtn = document.getElementById('cancelZlibModalBtn');
    const saveZlibModalBtn = document.getElementById('saveZlibModalBtn');
    const zlibKeyInput = document.getElementById('zlibKeyInput');
    const zlibUserIdInput = document.getElementById('zlibUserIdInput');
    const zlibStatusText = document.getElementById('zlibStatusText');
    const zlibStatusBadge = document.getElementById('zlibStatusBadge');

    const zlibTabLoginBtn = document.getElementById('zlibTabLoginBtn');
    const zlibTabManualBtn = document.getElementById('zlibTabManualBtn');
    const zlibLoginSection = document.getElementById('zlibLoginSection');
    const zlibManualSection = document.getElementById('zlibManualSection');
    const zlibDoLoginBtn = document.getElementById('zlibDoLoginBtn');
    const zlibLoginEmail = document.getElementById('zlibLoginEmail');
    const zlibLoginPassword = document.getElementById('zlibLoginPassword');
    const zlibLoginBtnText = document.getElementById('zlibLoginBtnText');

    // 重新整理 Z-Lib 狀態資訊
    async function refreshZlibStatus() {
      try {
        const res = await fetch('/api/zlib/config');
        if (res.ok) {
          const data = await res.json();
          if (data.has_token) {
            if (zlibStatusBadge) {
              zlibStatusBadge.textContent = '已授權綁定';
              zlibStatusBadge.className = 'text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30';
            }
            if (zlibStatusText) {
              const accDesc = data.email ? `帳號: ${data.email}` : `金鑰: ${data.token_preview}`;
              zlibStatusText.textContent = `目前狀態：已綁定 (${accDesc})，可直接一鍵高速下載 Z-Lib 完整 EPUB！`;
              zlibStatusText.className = "text-[11px] text-emerald-400 mt-1";
            }
            if (zlibKeyInput) zlibKeyInput.placeholder = `已配置: ${data.token_preview} (留空不修改)`;
            if (zlibUserIdInput && data.user_id) zlibUserIdInput.value = data.user_id;
            if (zlibLoginEmail && data.email) zlibLoginEmail.value = data.email;
          } else {
            if (zlibStatusBadge) {
              zlibStatusBadge.textContent = '未登入';
              zlibStatusBadge.className = 'text-[10px] px-2 py-0.5 rounded-full bg-slate-700 text-slate-300';
            }
            if (zlibStatusText) {
              zlibStatusText.textContent = "目前狀態：未設定 (支援線上免費檢索，下載原檔需登入帳號獲取配額)";
              zlibStatusText.className = "text-[11px] text-slate-400 mt-1";
            }
          }
        }
      } catch (e) {}
    }

    if (openZlibConfigBtn && zlibConfigModal) {
      openZlibConfigBtn.addEventListener('click', async () => {
        await refreshZlibStatus();
        zlibConfigModal.classList.remove('hidden');
        if (window.lucide) lucide.createIcons();
      });

      const hideZlibModal = () => zlibConfigModal.classList.add('hidden');
      if (closeZlibModalBtn) closeZlibModalBtn.addEventListener('click', hideZlibModal);
      if (cancelZlibModalBtn) cancelZlibModalBtn.addEventListener('click', hideZlibModal);

      // 分頁切換
      if (zlibTabLoginBtn && zlibTabManualBtn) {
        zlibTabLoginBtn.addEventListener('click', () => {
          zlibTabLoginBtn.className = 'flex-1 pb-2 text-center font-bold text-red-400 border-b-2 border-red-500 transition';
          zlibTabManualBtn.className = 'flex-1 pb-2 text-center text-slate-400 hover:text-white border-b-2 border-transparent transition';
          zlibLoginSection.classList.remove('hidden');
          zlibManualSection.classList.add('hidden');
        });
        zlibTabManualBtn.addEventListener('click', () => {
          zlibTabManualBtn.className = 'flex-1 pb-2 text-center font-bold text-red-400 border-b-2 border-red-500 transition';
          zlibTabLoginBtn.className = 'flex-1 pb-2 text-center text-slate-400 hover:text-white border-b-2 border-transparent transition';
          zlibManualSection.classList.remove('hidden');
          zlibLoginSection.classList.add('hidden');
        });
      }

      // 一鍵帳號密碼登入
      if (zlibDoLoginBtn && zlibLoginEmail && zlibLoginPassword) {
        zlibDoLoginBtn.addEventListener('click', async () => {
          const email = zlibLoginEmail.value.trim();
          const pwd = zlibLoginPassword.value.trim();
          if (!email || !pwd) {
            alert('請輸入 Z-Library 帳號 Email 與登入密碼！');
            return;
          }

          zlibDoLoginBtn.disabled = true;
          if (zlibLoginBtnText) zlibLoginBtnText.textContent = '正在登入連線中...';

          try {
            const res = await fetch('/api/zlib/login', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ email: email, password: pwd })
            });
            const data = await res.json();
            if (res.ok && data.success) {
              alert('🎉 Z-Library 登入成功！\n已為您自動綁定專屬金鑰與高速個人節點，現在可以一鍵暢快下載書籍！');
              await refreshZlibStatus();
              setTimeout(hideZlibModal, 800);
            } else {
              alert(`登入失敗：${data.detail || data.message || '請確認帳號密碼是否正確'}`);
            }
          } catch (e) {
            alert(`連線出錯: ${e.message}`);
          } finally {
            zlibDoLoginBtn.disabled = false;
            if (zlibLoginBtnText) zlibLoginBtnText.textContent = '立即登入並自動綁定';
          }
        });
      }

      // 手動儲存金鑰
      if (saveZlibModalBtn && zlibKeyInput) {
        saveZlibModalBtn.addEventListener('click', async () => {
          const key = zlibKeyInput.value.trim();
          const uid = zlibUserIdInput ? zlibUserIdInput.value.trim() : '';
          if (!key) {
            alert('請填寫 remix_user_key！');
            return;
          }
          try {
            const res = await fetch('/api/zlib/config', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ remix_user_key: key, remix_userid: uid })
            });
            if (res.ok) {
              alert('Z-Library 金鑰已成功儲存！');
              await refreshZlibStatus();
              hideZlibModal();
            } else {
              alert('儲存失敗，請重試');
            }
          } catch (e) {
            alert(`儲存出錯: ${e.message}`);
          }
        });
      }
    }
  }

  // 切換主導覽分頁
  function switchMainTab(tab) {
    const mainAppHeader = document.getElementById('mainAppHeader');
    const bookshelfView = document.getElementById('bookshelfView');
    const crawlerView = document.getElementById('crawlerView');
    const updatesView = document.getElementById('updatesView');
    const readerView = document.getElementById('readerView');
    const searchGroup = document.getElementById('bookshelfSearchGroup');

    // 確保全域導航列顯示
    if (mainAppHeader) mainAppHeader.classList.remove('hidden');

    // 關閉閱讀器
    if (readerView) readerView.classList.add('hidden');

    // 控制書櫃專屬搜尋列的顯示
    if (searchGroup) {
      if (tab === 'bookshelf') {
        searchGroup.classList.remove('invisible');
      } else {
        searchGroup.classList.add('invisible');
      }
    }

    const tabs = {
      bookshelf: { view: bookshelfView, nav: document.getElementById('navBookshelfBtn') },
      crawler: { view: crawlerView, nav: document.getElementById('navCrawlerBtn') },
      updates: { view: updatesView, nav: document.getElementById('navUpdatesBtn') }
    };

    Object.keys(tabs).forEach(k => {
      const item = tabs[k];
      if (item.view) {
        if (k === tab) {
          item.view.classList.remove('hidden');
        } else {
          item.view.classList.add('hidden');
        }
      }
      if (item.nav) {
        if (k === tab) {
          item.nav.classList.add('bg-red-600', 'text-white', 'shadow-md');
          item.nav.classList.remove('text-slate-300', 'hover:bg-slate-700');
        } else {
          item.nav.classList.remove('bg-red-600', 'text-white', 'shadow-md');
          item.nav.classList.add('text-slate-300', 'hover:bg-slate-700');
        }
      }
    });

    if (tab === 'bookshelf') {
      const searchInput = document.getElementById('searchInput');
      if (searchInput && (searchInput.value.includes('@') || !searchInput.dataset.userTyped)) {
        searchInput.value = '';
        if (window.AppState) window.AppState.searchQuery = '';
        const clearBtn = document.getElementById('clearSearchInputBtn');
        if (clearBtn) clearBtn.classList.add('hidden');
      }
      const fetchFn = window.fetchBooks || (typeof fetchBooks === 'function' ? fetchBooks : null);
      if (fetchFn) {
        fetchFn();
      }
    }

    if (window.lucide) {
      lucide.createIcons();
    }
  }

  // 載入支援網站列表並渲染站點切換 Tab
  async function loadSupportedSites() {
    try {
      const res = await fetch('/api/crawler/sites');
      if (res.ok) {
        supportedSites = await res.json();
        if (supportedSites.length > 0 && !supportedSites.some(s => s.id === currentSite)) {
          currentSite = supportedSites[0].id;
        }
        renderSiteTabs();
      }
    } catch (e) {
      console.error('載入站點失敗:', e);
    }
  }

  // 渲染站點切換 Tab
  function renderSiteTabs() {
    const container = document.getElementById('crawlerSiteTabs');
    if (!container) return;

    container.innerHTML = supportedSites.map(s => {
      const isActive = s.id === currentSite;
      return `
        <button class="site-tab-btn flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition border ${
          isActive 
            ? 'bg-slate-700 border-red-500/80 text-white shadow-sm ring-1 ring-red-500/40' 
            : 'bg-slate-800/80 border-slate-700 text-slate-300 hover:text-white hover:bg-slate-700/60'
        }" data-site="${s.id}">
          <span>${s.name}</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded-full ${
            isActive ? 'bg-red-500/20 text-red-300 border border-red-500/30' : 'bg-slate-700 text-slate-400'
          }">${s.badge}</span>
        </button>
      `;
    }).join('');

    container.querySelectorAll('.site-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        currentSite = btn.dataset.site;
        renderSiteTabs();
        loadExploreNovels(currentSite, currentCategory);
      });
    });
  }

  // 載入支援分類列表並渲染類別切換按鈕
  async function loadSupportedCategories() {
    try {
      const res = await fetch('/api/crawler/categories');
      if (res.ok) {
        supportedCategories = await res.json();
      } else {
        supportedCategories = [
          {"id": "all", "name": "全部推薦", "badge": "🔥 總榜"},
          {"id": "xuanhuan", "name": "玄幻奇幻", "badge": "⚔️ 玄幻"},
          {"id": "dushi", "name": "都市言情", "badge": "🏙️ 都市"},
          {"id": "wuxia", "name": "武俠仙俠", "badge": "🗡️ 仙俠"},
          {"id": "lishi", "name": "歷史軍事", "badge": "🛡️ 歷史"},
          {"id": "kehuan", "name": "科幻靈異", "badge": "🚀 科幻"},
          {"id": "youxi", "name": "遊戲競技", "badge": "🎮 遊戲"},
          {"id": "danmei", "name": "青春校園", "badge": "🌸 校園"}
        ];
      }
      renderCategoryTabs();
    } catch (e) {
      console.error('載入分類失敗:', e);
    }
  }

  // 渲染小說類別篩選按鈕
  function renderCategoryTabs() {
    const container = document.getElementById('crawlerCategoryTabs');
    if (!container) return;

    container.innerHTML = supportedCategories.map(cat => {
      const isActive = cat.id === currentCategory;
      return `
        <button class="category-tab-btn flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition border shrink-0 ${
          isActive 
            ? 'bg-red-600 text-white shadow-md shadow-red-900/40 border-red-500 ring-2 ring-red-500/30' 
            : 'bg-slate-700/60 border-slate-600/70 text-slate-300 hover:text-white hover:bg-slate-700'
        }" data-category="${cat.id}">
          <span>${cat.badge ? cat.badge : cat.name}</span>
        </button>
      `;
    }).join('');

    container.querySelectorAll('.category-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        currentCategory = btn.dataset.category;
        renderCategoryTabs();
        loadExploreNovels(currentSite, currentCategory);
      });
    });
  }

  // 探索站點推薦/排行小說 (支援分類篩選)
  async function loadExploreNovels(siteId, categoryId = 'all') {
    const grid = document.getElementById('crawlerBooksGrid');
    const loading = document.getElementById('crawlerLoadingPrompt');
    const countEl = document.getElementById('crawlerBooksCount');
    if (!grid) return;

    grid.innerHTML = '';
    if (loading) loading.classList.remove('hidden');

    try {
      const res = await fetch(`/api/crawler/explore?site=${siteId}&category=${categoryId || 'all'}`);
      if (res.ok) {
        const novels = await res.json();
        renderNovelsGrid(novels);
        if (countEl) countEl.textContent = novels.length;
      } else {
        grid.innerHTML = `<div class="col-span-full py-12 text-center text-slate-400">目前無法載入該網站推薦內容，請嘗試搜尋或直接輸入網址。</div>`;
        if (countEl) countEl.textContent = '0';
      }
    } catch (e) {
      grid.innerHTML = `<div class="col-span-full py-12 text-center text-red-400">連線失敗: ${e.message}</div>`;
      if (countEl) countEl.textContent = '0';
    } finally {
      if (loading) loading.classList.add('hidden');
      if (window.lucide) lucide.createIcons();
    }
  }

  // 搜尋處理
  async function handleSearch() {
    const input = document.getElementById('crawlerSearchInput');
    const kw = input ? input.value.trim() : '';
    if (!kw) return;

    const grid = document.getElementById('crawlerBooksGrid');
    const loading = document.getElementById('crawlerLoadingPrompt');
    if (!grid) return;

    // 若使用者輸入為 URL，直接觸發解析彈窗
    if (kw.startsWith('http://') || kw.startsWith('https://') || kw.includes('.com') || kw.includes('.tw')) {
      openBookDetail(kw);
      return;
    }

    grid.innerHTML = '';
    if (loading) loading.classList.remove('hidden');

    try {
      const res = await fetch(`/api/crawler/search?keyword=${encodeURIComponent(kw)}&site=${currentSite}`);
      if (res.ok) {
        const results = await res.json();
        if (results.length === 0) {
          grid.innerHTML = `
            <div class="col-span-full py-12 text-center text-slate-400">
              <i data-lucide="search-x" class="w-12 h-12 mx-auto mb-3 text-slate-500"></i>
              <p class="text-base font-medium">未找到「${kw}」相關小說</p>
              <p class="text-xs text-slate-500 mt-1">您可以切換上方站點再次搜尋，或直接貼入該小說目錄網址。</p>
            </div>
          `;
        } else {
          renderNovelsGrid(results);
        }
      }
    } catch (e) {
      grid.innerHTML = `<div class="col-span-full py-12 text-center text-red-400">搜尋出錯: ${e.message}</div>`;
    } finally {
      if (loading) loading.classList.add('hidden');
      if (window.lucide) lucide.createIcons();
    }
  }

  // 渲染小說卡片網格
  function renderNovelsGrid(novels) {
    const grid = document.getElementById('crawlerBooksGrid');
    const countEl = document.getElementById('crawlerBooksCount');
    if (!grid) return;

    if (countEl) countEl.textContent = novels ? novels.length : 0;

    if (!novels || novels.length === 0) {
      grid.innerHTML = `<div class="col-span-full py-12 text-center text-slate-400">無書籍內容</div>`;
      return;
    }

    grid.innerHTML = novels.map(n => {
      // 高質感排行榜名次標籤
      let rankBadgeHtml = '';
      if (n.badge) {
        if (n.badge.includes('TOP 1') || n.rank === 1) {
          rankBadgeHtml = `<span class="text-[11px] px-2.5 py-0.5 rounded-full bg-gradient-to-r from-amber-400 to-yellow-500 text-slate-950 font-black shadow-md flex items-center gap-1">${n.badge}</span>`;
        } else if (n.badge.includes('TOP 2') || n.rank === 2) {
          rankBadgeHtml = `<span class="text-[11px] px-2.5 py-0.5 rounded-full bg-gradient-to-r from-slate-200 to-slate-400 text-slate-950 font-bold shadow-md flex items-center gap-1">${n.badge}</span>`;
        } else if (n.badge.includes('TOP 3') || n.rank === 3) {
          rankBadgeHtml = `<span class="text-[11px] px-2.5 py-0.5 rounded-full bg-gradient-to-r from-amber-600 to-orange-600 text-white font-bold shadow-md flex items-center gap-1">${n.badge}</span>`;
        } else {
          rankBadgeHtml = `<span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-700/80 border border-slate-600 text-slate-200 font-semibold">${n.badge}</span>`;
        }
      }

      const coverHtml = n.cover_url 
        ? `<img src="${n.cover_url}" alt="${n.title}" class="w-full h-full object-cover rounded-lg shadow group-hover:scale-105 transition duration-300" onerror="this.outerHTML='<div class=\\\'w-full h-full rounded-lg bg-gradient-to-br from-slate-700 to-slate-800 flex items-center justify-center p-2 text-center text-xs font-bold text-slate-300\\\'>${n.title}</div>'">`
        : `<div class="w-full h-full rounded-lg bg-gradient-to-br from-slate-700 via-slate-800 to-slate-900 border border-slate-700/60 flex flex-col justify-between p-3 text-slate-300 group-hover:border-red-500/40 transition">
             <div class="text-[10px] text-red-400 font-semibold uppercase tracking-wider">${n.site_name || 'ONLINE'}</div>
             <div class="text-sm font-bold text-white line-clamp-3 leading-snug">${n.title}</div>
             <div class="text-[11px] text-slate-400 truncate">${n.author || '網路作家'}</div>
           </div>`;

      // 類別標籤字樣優化
      let catBadgeHtml = '';
      if (n.category && n.category !== 'all') {
        catBadgeHtml = `<span class="text-[10px] px-2 py-0.5 rounded-full bg-red-950/70 border border-red-500/40 text-red-300 font-medium">${n.category}</span>`;
      }

      return `
        <div class="group bg-slate-800/85 hover:bg-slate-800 border ${n.rank <= 3 ? 'border-amber-500/60 shadow-amber-950/20' : 'border-slate-700/70'} hover:border-red-500/50 rounded-2xl p-4 flex flex-col justify-between transition-all duration-200 shadow-md hover:shadow-red-950/20">
          <div class="flex gap-4">
            <div class="w-24 h-32 shrink-0 overflow-hidden rounded-lg bg-slate-900 shadow-inner relative">
              ${coverHtml}
              ${n.rank <= 3 ? `<div class="absolute top-1 left-1 w-5 h-5 rounded-full bg-red-600 text-white text-[10px] font-bold flex items-center justify-center shadow">${n.rank}</div>` : ''}
            </div>
            <div class="flex-1 min-w-0 flex flex-col justify-between">
              <div>
                <div class="flex items-center gap-1.5 mb-1.5 flex-wrap">
                  ${rankBadgeHtml}
                  <span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-700/80 text-slate-300 font-medium">
                    ${n.site_name || '站點'}
                  </span>
                  ${catBadgeHtml}
                </div>
                <h3 class="text-base font-bold text-white group-hover:text-red-400 transition line-clamp-2 leading-snug" title="${n.title}">
                  ${n.title}
                </h3>
                <p class="text-xs text-slate-400 mt-1 truncate">
                  作者：<span class="text-slate-300 font-medium">${n.author || '佚名'}</span>
                </p>
                ${n.intro ? `<p class="text-[11px] text-slate-400/90 mt-1.5 line-clamp-2 leading-relaxed bg-slate-900/40 p-1.5 rounded-lg border border-slate-700/30">${n.intro}</p>` : ''}
              </div>
              
              <div class="mt-3">
                <button class="view-detail-btn w-full py-2 px-3 rounded-xl bg-slate-700 hover:bg-red-600 text-white text-xs font-semibold flex items-center justify-center gap-1.5 transition shadow" data-url="${n.url}">
                  <i data-lucide="book-open" class="w-3.5 h-3.5"></i>
                  <span>詳情與下載</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      `;
    }).join('');

    grid.querySelectorAll('.view-detail-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const targetUrl = btn.dataset.url;
        // 若為 Z-Library 書籍直接啟動下載
        if (targetUrl && targetUrl.includes('z-lib.by')) {
          startDownload(targetUrl);
        } else {
          openBookDetail(targetUrl);
        }
      });
    });

    if (window.lucide) lucide.createIcons();
  }

  // 開啟書籍詳情彈窗
  async function openBookDetail(url) {
    const modal = document.getElementById('crawlerDetailModal');
    if (!modal) return;

    modal.classList.remove('hidden');
    const loadingState = document.getElementById('detailModalLoading');
    const contentState = document.getElementById('detailModalContent');
    const errorState = document.getElementById('detailModalError');

    if (loadingState) loadingState.classList.remove('hidden');
    if (contentState) contentState.classList.add('hidden');
    if (errorState) errorState.classList.add('hidden');

    try {
      const res = await fetch('/api/crawler/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '書籍解析失敗');
      }

      const book = await res.json();
      renderBookDetailModal(book);

      if (loadingState) loadingState.classList.add('hidden');
      if (contentState) contentState.classList.remove('hidden');
    } catch (e) {
      if (loadingState) loadingState.classList.add('hidden');
      if (errorState) {
        errorState.classList.remove('hidden');
        document.getElementById('detailErrorMessage').textContent = e.message;
      }
    } finally {
      if (window.lucide) lucide.createIcons();
    }
  }

  // 渲染書籍詳情資訊
  function renderBookDetailModal(book) {
    document.getElementById('detailModalTitle').textContent = book.title;
    document.getElementById('detailModalAuthor').textContent = book.author || '佚名';
    document.getElementById('detailModalSite').textContent = book.site || '未知來源';
    document.getElementById('detailModalTotalChaps').textContent = `${book.total_chapters} 章`;
    document.getElementById('detailModalLatestChap').textContent = book.latest_chapter || '無';
    document.getElementById('detailModalIntro').textContent = book.intro || '暫無作品簡介';

    const coverImg = document.getElementById('detailModalCover');
    if (coverImg) {
      if (book.cover_url) {
        coverImg.src = book.cover_url;
        coverImg.classList.remove('hidden');
      } else {
        coverImg.classList.add('hidden');
      }
    }

    // 章節前覽
    const chapsList = document.getElementById('detailModalChapsList');
    if (chapsList) {
      chapsList.innerHTML = (book.first_chapters || []).map((ch, idx) => `
        <div class="text-xs text-slate-300 py-1 border-b border-slate-700/50 flex items-center justify-between">
          <span class="truncate">${ch}</span>
          <span class="text-[10px] text-slate-500">第 ${idx + 1} 章</span>
        </div>
      `).join('');
    }

    // 綁定立即下載按鈕
    const downloadBtn = document.getElementById('startDownloadBookBtn');
    if (downloadBtn) {
      // 移除舊 listener
      const newBtn = downloadBtn.cloneNode(true);
      downloadBtn.parentNode.replaceChild(newBtn, downloadBtn);
      
      newBtn.addEventListener('click', () => {
        document.getElementById('crawlerDetailModal').classList.add('hidden');
        startDownload(book.dir_url);
      });
    }
  }

  // 開始下載小說
  async function startDownload(url) {
    try {
      showFloatingProgress('正在啟動下載工作...', 5);

      const res = await fetch('/api/crawler/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url, export_format: 'epub' })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '啟動下載失敗');
      }

      const data = await res.json();
      activeTaskId = data.task_id;
      pollDownloadProgress(activeTaskId);
    } catch (e) {
      updateFloatingProgressError(e.message);
    }
  }

  // 輪詢下載任務進度
  function pollDownloadProgress(taskId) {
    if (taskPollTimer) clearInterval(taskPollTimer);

    taskPollTimer = setInterval(async () => {
      try {
        const res = await fetch(`/api/crawler/tasks/${taskId}`);
        if (!res.ok) return;

        const task = await res.json();
        updateFloatingProgressDisplay(task);

        if (task.status === 'completed') {
          clearInterval(taskPollTimer);
          taskPollTimer = null;
          handleDownloadCompleted(task);
        } else if (task.status === 'error') {
          clearInterval(taskPollTimer);
          taskPollTimer = null;
          updateFloatingProgressError(task.message || task.error || '下載出錯', task);
        }
      } catch (e) {
        console.warn('輪詢進度失敗:', e);
      }
    }, 800);
  }

  // 顯示浮動進度視窗
  function showFloatingProgress(msg, pct) {
    const bar = document.getElementById('crawlerFloatingProgress');
    if (!bar) return;

    bar.classList.remove('hidden');
    document.getElementById('floatingProgressMsg').textContent = msg;
    document.getElementById('floatingProgressBar').className = 'bg-gradient-to-r from-red-600 to-amber-500 h-full transition-all duration-300';
    document.getElementById('floatingProgressBar').style.width = `${pct}%`;
    document.getElementById('floatingProgressPct').textContent = `${pct}%`;
    document.getElementById('floatingSuccessAction').classList.add('hidden');
    const errBox = document.getElementById('floatingErrorAction');
    if (errBox) errBox.classList.add('hidden');
  }

  // 更新進度顯示
  function updateFloatingProgressDisplay(task) {
    const bar = document.getElementById('crawlerFloatingProgress');
    if (!bar) return;

    bar.classList.remove('hidden');
    document.getElementById('floatingProgressTitle').textContent = task.title || '小說下載中';
    document.getElementById('floatingProgressMsg').textContent = task.message || '正文抓取中...';
    document.getElementById('floatingProgressBar').style.width = `${task.progress}%`;
    document.getElementById('floatingProgressPct').textContent = `${task.progress}%`;

    const subInfo = document.getElementById('floatingProgressSub');
    if (subInfo && task.total > 0) {
      subInfo.textContent = `[${task.current || 0}/${task.total}] ${task.current_chapter || ''}`;
    }
  }

  // 下載完成處理
  function handleDownloadCompleted(task) {
    const successBox = document.getElementById('floatingSuccessAction');
    const readBtn = document.getElementById('floatingReadNowBtn');
    if (successBox) successBox.classList.remove('hidden');

    // 重新抓取書櫃資料
    const refreshFn = window.fetchBooks || (typeof fetchBooks === 'function' ? fetchBooks : null);
    if (refreshFn) {
      refreshFn();
    }

    // 綁定立即閱讀按鈕
    if (readBtn) {
      readBtn.onclick = async () => {
        // 隱藏下載浮動進度面板
        const bar = document.getElementById('crawlerFloatingProgress');
        if (bar) bar.classList.add('hidden');

        // 先切換到書櫃以確保 DOM 結構正常
        switchMainTab('bookshelf');

        // 呼叫閱讀器開啟此書籍
        const openFn = window.openBookById || (typeof openBookById === 'function' ? openBookById : null);
        if (openFn) {
          let targetId = task.book_uuid;
          // 若無直接 uuid，嘗試從最新刷新後的列表比對檔名或書名
          if (!targetId && window.AppState && window.AppState.books && window.AppState.books.length > 0) {
            const found = window.AppState.books.find(b => 
              (task.book_file && b.file_name && b.file_name.includes(task.book_file)) ||
              (task.title && b.title && b.title.includes(task.title))
            );
            if (found) targetId = found.id;
          }
          if (targetId) {
            await openFn(targetId);
          } else {
            console.warn('未找到目標書籍 UUID，已返回書櫃');
          }
        }
      };
    }
  }

  // 顯示下載錯誤
  function updateFloatingProgressError(errMsg, task = null) {
    const bar = document.getElementById('crawlerFloatingProgress');
    if (!bar) return;

    bar.classList.remove('hidden');
    document.getElementById('floatingProgressMsg').textContent = `錯誤: ${errMsg}`;
    document.getElementById('floatingProgressBar').className = 'h-full transition-all duration-300 bg-red-600';
    document.getElementById('floatingProgressBar').style.width = `100%`;
    document.getElementById('floatingSuccessAction').classList.add('hidden');

    const errBox = document.getElementById('floatingErrorAction');
    const openZlibBtn = document.getElementById('floatingOpenZlibModalBtn');
    const directBtn = document.getElementById('floatingWebDirectBtn');

    if (errBox) {
      const isZlib = (errMsg && (errMsg.includes('Z-Library') || errMsg.includes('Z-Lib') || errMsg.includes('AUTH_'))) ||
                     (task && task.web_url);
      if (isZlib) {
        errBox.classList.remove('hidden');
        if (directBtn) {
          const directUrl = (task && task.web_url) ? task.web_url : 'https://zh.z-lib.by';
          directBtn.href = directUrl;
        }
        if (openZlibBtn) {
          openZlibBtn.onclick = () => {
            const zlibBtn = document.getElementById('openZlibConfigBtn');
            if (zlibBtn) zlibBtn.click();
          };
        }
      } else {
        errBox.classList.add('hidden');
      }
    }
    if (window.lucide) lucide.createIcons();
  }

  // ==================== 追更管理模組 (Updates View) ====================

  // 載入已追蹤線上小說列表
  async function loadTrackedNovels() {
    const container = document.getElementById('trackedNovelsContainer');
    const loading = document.getElementById('trackedLoadingPrompt');
    if (!container) return;

    container.innerHTML = '';
    if (loading) loading.classList.remove('hidden');

    try {
      const res = await fetch('/api/crawler/tracked');
      if (res.ok) {
        trackedBooks = await res.json();
        renderTrackedBooksList();
      }
    } catch (e) {
      container.innerHTML = `<div class="py-12 text-center text-red-400">載入追更清單出錯: ${e.message}</div>`;
    } finally {
      if (loading) loading.classList.add('hidden');
      if (window.lucide) lucide.createIcons();
    }
  }

  // 渲染追更書籍卡片列表
  function renderTrackedBooksList(query = '') {
    const container = document.getElementById('trackedNovelsContainer');
    const statTotal = document.getElementById('statTrackedTotal');
    const statPending = document.getElementById('statTrackedPending');
    if (!container) return;

    let filtered = trackedBooks;
    if (query) {
      filtered = trackedBooks.filter(b => 
        (b.title && b.title.toLowerCase().includes(query)) ||
        (b.author && b.author.toLowerCase().includes(query))
      );
    }

    if (statTotal) statTotal.textContent = `${trackedBooks.length} 本`;

    // 計算可更新數量
    const pendingCount = Object.values(updateCheckResults).filter(r => r.has_update).length;
    if (statPending) statPending.textContent = `${pendingCount} 本`;

    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="py-16 text-center text-slate-400">
          <i data-lucide="layers" class="w-14 h-14 mx-auto mb-3 text-slate-600"></i>
          <p class="text-lg font-bold text-slate-300">目前沒有追更書籍</p>
          <p class="text-sm text-slate-500 mt-1">從「小說抓取」頁面下載的線上小說將會自動加入此追更書架！</p>
        </div>
      `;
      if (window.lucide) lucide.createIcons();
      return;
    }

    container.innerHTML = filtered.map(b => {
      const checkRes = updateCheckResults[b.book_key];
      const hasUpdate = checkRes && checkRes.has_update;
      const latestCount = checkRes ? checkRes.latest_count : b.downloaded_count;
      const diffCount = checkRes ? checkRes.new_count : 0;

      return `
        <div class="bg-slate-800/80 hover:bg-slate-800 border ${hasUpdate ? 'border-amber-500/80 shadow-amber-950/20' : 'border-slate-700/70'} rounded-2xl p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 transition shadow-md">
          <div class="flex items-center gap-4 min-w-0">
            <div class="w-14 h-20 rounded-lg bg-slate-900 border border-slate-700/60 overflow-hidden shrink-0 flex items-center justify-center">
              ${b.cover_url 
                ? `<img src="${b.cover_url}" class="w-full h-full object-cover">` 
                : `<i data-lucide="book" class="w-6 h-6 text-slate-600"></i>`}
            </div>
            
            <div class="min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <h3 class="text-base font-bold text-white truncate max-w-md">${b.title}</h3>
                <span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">${b.source || '站點'}</span>
                ${hasUpdate 
                  ? `<span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-500 text-slate-950 font-bold animate-pulse">有 ${diffCount} 個新章節！</span>` 
                  : `<span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">已是最新</span>`}
              </div>
              
              <p class="text-xs text-slate-400 flex items-center gap-3">
                <span>作者：${b.author || '佚名'}</span>
                <span>·</span>
                <span>已下載：<b class="text-white">${b.downloaded_count}</b> 章</span>
                <span>·</span>
                <span>最新：<b class="text-white">${latestCount}</b> 章</span>
              </p>
              
              <p class="text-xs text-slate-500 mt-1 truncate max-w-lg">
                最後章節：${b.last_chapter_title || '無'}
              </p>
            </div>
          </div>

          <!-- 操作按鈕 -->
          <div class="flex items-center gap-2 w-full md:w-auto shrink-0 justify-end">
            <button class="check-single-btn px-3 py-2 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition" data-key="${b.book_key}">
              <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
              <span>檢查更新</span>
            </button>
            
            ${hasUpdate ? `
              <button class="apply-single-btn px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold flex items-center gap-1.5 transition shadow-lg shadow-amber-950/40" data-key="${b.book_key}">
                <i data-lucide="download" class="w-3.5 h-3.5"></i>
                <span>立即更新 (+${diffCount})</span>
              </button>
            ` : ''}

            <button class="read-single-btn px-3 py-2 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition" data-uuid="${b.file_uuid || ''}">
              <i data-lucide="book-open" class="w-3.5 h-3.5"></i>
              <span>閱讀</span>
            </button>

            <button class="delete-tracked-btn px-2.5 py-2 rounded-xl bg-slate-700/60 hover:bg-red-600/80 text-slate-400 hover:text-white text-xs font-semibold flex items-center gap-1 transition" data-key="${b.book_key}" data-title="${b.title}" title="從追更管理中移除">
              <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
              <span>刪除</span>
            </button>
          </div>
        </div>
      `;
    }).join('');

    // 綁定卡片按鈕事件
    container.querySelectorAll('.check-single-btn').forEach(btn => {
      btn.addEventListener('click', () => handleCheckSingleUpdate(btn.dataset.key));
    });

    container.querySelectorAll('.apply-single-btn').forEach(btn => {
      btn.addEventListener('click', () => handleApplyUpdate(btn.dataset.key));
    });

    container.querySelectorAll('.read-single-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const uuid = btn.dataset.uuid;
        switchMainTab('bookshelf');
        if (uuid && typeof window.openBookById === 'function') {
          window.openBookById(uuid);
        }
      });
    });

    container.querySelectorAll('.delete-tracked-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const key = btn.dataset.key;
        const title = btn.dataset.title;
        if (confirm(`確定要將《${title}》從追更管理中移除嗎？\n（已入庫之電子書仍會完整保留於書櫃中）`)) {
          try {
            let res = await fetch('/api/crawler/delete-tracked', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ book_key: key })
            });
            if (!res.ok) {
              res = await fetch(`/api/crawler/tracked/${encodeURIComponent(key)}`, { method: 'DELETE' });
            }
            if (res.ok) {
              trackedBooks = trackedBooks.filter(x => x.book_key !== key);
              delete updateCheckResults[key];
              renderTrackedBooksList();
            } else {
              const errData = await res.json().catch(() => ({}));
              alert(`移除失敗: ${errData.detail || '請檢查伺服器是否已重新啟動'}`);
            }
          } catch (err) {
            alert(`刪除出錯: ${err.message}`);
          }
        }
      });
    });

    if (window.lucide) lucide.createIcons();
  }

  // 雙向同步書庫與追更
  async function handleSyncBookshelf() {
    const btn = document.getElementById('syncBookshelfBtn');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<i data-lucide="loader" class="w-3.5 h-3.5 animate-spin"></i><span>同步中...</span>`;
      if (window.lucide) lucide.createIcons();
    }
    try {
      const res = await fetch('/api/crawler/sync-bookshelf', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        await loadTrackedNovels();
        if (typeof window.fetchBooks === 'function') {
          window.fetchBooks();
        }
        alert(`🎉 書庫同步成功！\n- 新增入庫書籍：${data.data.imported_books} 本\n- 追更書籍總計：${data.data.total_tracked} 本\n- 書櫃藏書總計：${data.data.total_shelf} 本`);
      } else {
        alert('同步失敗');
      }
    } catch (e) {
      alert(`同步失敗: ${e.message}`);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<i data-lucide="folder-sync" class="w-3.5 h-3.5 text-sky-400"></i><span>同步書庫</span>`;
        if (window.lucide) lucide.createIcons();
      }
    }
  }

  // 檢查單本更新
  async function handleCheckSingleUpdate(bookKey) {
    try {
      const btn = document.querySelector(`.check-single-btn[data-key="${bookKey}"]`);
      if (btn) btn.innerHTML = `<i data-lucide="loader" class="w-3.5 h-3.5 animate-spin"></i><span>檢查中...</span>`;
      if (window.lucide) lucide.createIcons();

      const res = await fetch('/api/crawler/check-updates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ book_key: bookKey })
      });

      if (res.ok) {
        const results = await res.json();
        if (results.length > 0) {
          updateCheckResults[bookKey] = results[0];
          renderTrackedBooksList();
        }
      }
    } catch (e) {
      alert(`檢查失敗: ${e.message}`);
    }
  }

  // 一鍵檢查全部更新
  async function handleCheckAllUpdates() {
    const btn = document.getElementById('checkAllUpdatesBtn');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin"></i><span>正在檢查全部更新...</span>`;
      if (window.lucide) lucide.createIcons();
    }

    try {
      const res = await fetch('/api/crawler/check-updates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ all_books: true })
      });

      if (res.ok) {
        const results = await res.json();
        results.forEach(r => {
          if (r.book_key) updateCheckResults[r.book_key] = r;
        });
        renderTrackedBooksList();
      }
    } catch (e) {
      alert(`檢查更新失敗: ${e.message}`);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<i data-lucide="refresh-cw" class="w-4 h-4"></i><span>檢查全部更新</span>`;
        if (window.lucide) lucide.createIcons();
      }
    }
  }

  // 執行增量追更下載
  async function handleApplyUpdate(bookKey) {
    try {
      showFloatingProgress('正在啟動增量追更下載...', 5);

      const res = await fetch('/api/crawler/apply-update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ book_key: bookKey })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '啟動更新失敗');
      }

      const data = await res.json();
      activeTaskId = data.task_id;
      pollDownloadProgress(activeTaskId);

      // 下載完成後清除該書的更新標記
      delete updateCheckResults[bookKey];
    } catch (e) {
      updateFloatingProgressError(e.message);
    }
  }

  // 導出對外介面
  return {
    init,
    switchMainTab,
    openBookDetail,
    startDownload
  };
})();

// 當 DOM 準備完成後初始化 CrawlerModule
document.addEventListener('DOMContentLoaded', () => {
  CrawlerModule.init();
});
