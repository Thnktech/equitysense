document.addEventListener('DOMContentLoaded', () => {
    console.log("System initializing...");

    const Store = {
        portfolio: JSON.parse(localStorage.getItem('ep_portfolio')) || [],
        settings: JSON.parse(localStorage.getItem('ep_settings')) || { currency: 'USD' },
        profile: JSON.parse(localStorage.getItem('ep_profile')) || null,
        cache: JSON.parse(localStorage.getItem('ep_cache')) || {},
        exchangeRate: 1.0,
        
        getApiKey: () => sessionStorage.getItem('ep_api_key'),
        setApiKey: (key) => sessionStorage.setItem('ep_api_key', key),
        savePortfolio: () => localStorage.setItem('ep_portfolio', JSON.stringify(Store.portfolio)),
        saveProfile: () => localStorage.setItem('ep_profile', JSON.stringify(Store.profile)),
        saveCache: () => localStorage.setItem('ep_cache', JSON.stringify(Store.cache)),
        saveSettings: () => localStorage.setItem('ep_settings', JSON.stringify(Store.settings)),
        generateId: () => '_' + Math.random().toString(36).substr(2, 9)
    };

    // ... [InvestorTypes and getRebalanceLimits remain identical to previous versions] ...
    const InvestorTypes = {
        "Compounder": { id: 1, name: "Long-Term Compounder", desc: "Maximizes long-term intrinsic value.", weights: { growth: 0.4, quality: 0.4, safety: 0.1, value: 0.1 }, pillars:['growth','quality'] },
        "Redeployer": { id: 2, name: "Capital Redeployer", desc: "Reallocates capital to best opportunities.", weights: { value: 0.4, momentum: 0.2, growth: 0.2, safety: 0.2 }, pillars:['value','growth'] },
        "CashConstrained": { id: 3, name: "Cash-Constrained", desc: "Grows capital with limited surplus.", weights: { safety: 0.5, value: 0.3, quality: 0.2, growth: 0.0 }, pillars:['safety','value'] },
        "Income": { id: 4, name: "Income-Focused", desc: "Prioritizes stable cash flows.", weights: { dividend: 0.5, safety: 0.3, quality: 0.2, growth: 0.0 }, pillars:['safety'] },
        "RiskMinimizer": { id: 5, name: "Risk-Minimizer", desc: "Capital preservation is paramount.", weights: { safety: 0.6, quality: 0.3, value: 0.1, growth: 0.0 }, pillars:['safety','quality'] },
        "DrawdownSensitive": { id: 6, name: "Drawdown-Sensitive", desc: "Strict loss limits.", weights: { safety: 0.5, momentum: 0.2, quality: 0.3, growth: 0.0 }, pillars:['safety','value'] },
        "TimeHorizon": { id: 7, name: "Time-Horizon Optimizer", desc: "Maximizes capital for future date.", weights: { growth: 0.5, quality: 0.3, value: 0.2, safety: 0.0 }, pillars:['growth'] },
        "VolatilityAgnostic": { id: 8, name: "Volatility-Agnostic", desc: "CAGR above all else.", weights: { growth: 0.6, momentum: 0.2, value: 0.2, safety: 0.0 }, pillars:['growth','quality'] },
        "LiquidityConstrained": { id: 9, name: "Liquidity-Constrained", desc: "Needs near-term access to cash.", weights: { safety: 0.4, quality: 0.4, momentum: 0.2, growth: 0.0 }, pillars:['safety'] },
        "Concentrator": { id: 10, name: "Conviction-Weighted", desc: "Outsized returns via few bets.", weights: { quality: 0.5, growth: 0.3, value: 0.2, safety: 0.0 }, pillars:['growth','quality'] },
        "Stabilizer": { id: 11, name: "Diversification-First", desc: "Reduces idiosyncratic risk.", weights: { safety: 0.4, quality: 0.4, value: 0.2, growth: 0.0 }, pillars:['safety','quality'] },
        "ValuationAnchored": { id: 12, name: "Valuation-Anchored", desc: "Only buys with Margin of Safety.", weights: { value: 0.7, quality: 0.2, safety: 0.1, growth: 0.0 }, pillars:['value','safety'] },
        "Systematic": { id: 13, name: "Rule-Bound Systematic", desc: "Strict adherence to rules.", weights: { quality: 0.3, value: 0.3, safety: 0.3, growth: 0.1 }, pillars:['value','quality'] },
        "CycleTimer": { id: 14, name: "Opportunistic Cycle-Timer", desc: "Exploits market cycles.", weights: { value: 0.4, momentum: 0.4, quality: 0.2, safety: 0.0 }, pillars:['value','growth'] },
        "PreservationPlus": { id: 15, name: "Capital-Preservation-Plus", desc: "Beat inflation, low risk.", weights: { safety: 0.7, quality: 0.2, dividend: 0.1, growth: 0.0 }, pillars:['safety','value'] }
    };

    const getRebalanceLimits = (typeKey) => {
        if (!typeKey) return { max: 0.15 };
        if (typeKey === "Concentrator" || typeKey === "Compounder") return { max: 0.25 };
        if (typeKey === "RiskMinimizer" || typeKey === "Stabilizer") return { max: 0.10 };
        return { max: 0.15 };
    };

    const API = {
        baseUrl: 'https://www.alphavantage.co/query',
        queue: [],
        isProcessing: false,
        enqueue: (params, callback) => {
            API.queue.push({ params, callback });
            UI.updateQueue(API.queue.length);
            API.process();
        },
        process: async () => {
            if (API.isProcessing || API.queue.length === 0) return;
            API.isProcessing = true;
            const task = API.queue.shift();
            UI.updateQueue(API.queue.length, true);
            try {
                let data;
                if(task.params.function === 'OVERVIEW' && Store.cache[task.params.symbol] && (Date.now() - Store.cache[task.params.symbol].ts < 86400000)) {
                    data = Store.cache[task.params.symbol].data;
                } else {
                    data = await API.fetchData(task.params);
                    if(task.params.function === 'OVERVIEW' && !data.Note && !data.Information) {
                        Store.cache[task.params.symbol] = { data: data, ts: Date.now() };
                        Store.saveCache();
                    }
                }
                task.callback(data);
            } catch (err) { console.error(err); UI.toast("API Error", "error"); }
            
            let countdown = 120; 
            const timer = setInterval(() => {
                countdown--;
                UI.updateProgress((120 - countdown) / 120 * 100);
                if (countdown <= 0) {
                    clearInterval(timer);
                    UI.updateProgress(0);
                    API.isProcessing = false;
                    API.process();
                }
            }, 100);
        },
        fetchData: async (params) => {
            const key = Store.getApiKey();
            if (!key) throw new Error("Missing API Key");
            const url = `${API.baseUrl}?` + new URLSearchParams({ ...params, apikey: key });
            const res = await fetch(url);
            return await res.json();
        },
        fetchExchangeRate: async () => {
            if (!Store.getApiKey()) return;
            try {
                const data = await API.fetchData({ function: 'CURRENCY_EXCHANGE_RATE', from_currency: 'USD', to_currency: 'EUR' });
                if(data['Realtime Currency Exchange Rate']) Store.exchangeRate = parseFloat(data['Realtime Currency Exchange Rate']['5. Exchange Rate']);
            } catch(e) { Store.exchangeRate = 0.95; }
        }
    };

    const UI = {
        toast: (msg, type = 'info') => {
            const el = document.createElement('div');
            el.className = `toast`;
            el.style.borderLeftColor = type === 'error' ? 'var(--danger)' : 'var(--success)';
            el.innerText = msg;
            document.getElementById('toastContainer').appendChild(el);
            setTimeout(() => el.remove(), 4000);
        },
        updateQueue: (count, active) => document.getElementById('apiQueueLabel').innerText = active ? `Processing (${count})...` : 'Queue: Idle',
        updateProgress: (pct) => document.getElementById('apiProgressBar').style.width = `${pct}%`,
        fmtMoney: (n) => {
            let val = n; let code = 'USD';
            if (Store.settings.currency === 'EUR') { val = n * Store.exchangeRate; code = 'EUR'; }
            return new Intl.NumberFormat('en-US', { style: 'currency', currency: code }).format(val);
        },
        fmtPct: (n) => `${(n).toFixed(2)}%`,
        
        renderPortfolio: () => {
            const tbody = document.getElementById('portfolioList');
            if (!tbody) return;
            tbody.innerHTML = '';
            let totalInv = 0, totalVal = 0;
            Store.portfolio.forEach((stock, idx) => {
                const sShares = parseFloat(stock.shares);
                const sPrice = parseFloat(stock.price);
                const sCurr = stock.currentPrice ? parseFloat(stock.currentPrice) : sPrice;
                const val = sCurr * sShares;
                const cost = sPrice * sShares;
                let ret = 0;
                if(sCurr && sCurr !== sPrice) ret = ((val - cost) / cost) * 100;
                totalInv += cost; totalVal += val;
                const tr = document.createElement('tr');
                tr.innerHTML = `<td style="font-weight:700; font-family: var(--font-mono)">${stock.symbol}</td><td>${sShares}</td><td>${UI.fmtMoney(sPrice)}</td><td style="color:${stock.currentPrice?'':'var(--text-secondary)'}">${stock.currentPrice?UI.fmtMoney(sCurr):'Pending...'}</td><td>${UI.fmtMoney(val)}</td><td class="${ret>0?'positive':(ret<0?'negative':'')}">${UI.fmtPct(ret)}</td><td>${stock.conviction}</td><td><button class="btn-icon action-btn refresh-btn" data-index="${idx}" title="Update"><i class="fa-solid fa-rotate"></i></button><button class="btn-icon action-btn edit-btn" data-index="${idx}"><i class="fa-solid fa-pen"></i></button><button class="btn-icon action-btn delete-btn" data-id="${stock.id}" style="color:var(--danger)"><i class="fa-solid fa-trash"></i></button></td>`;
                tbody.appendChild(tr);
            });
            document.getElementById('totalInvested').innerText = UI.fmtMoney(totalInv);
            document.getElementById('totalValue').innerText = UI.fmtMoney(totalVal);
            const ret = totalInv > 0 ? ((totalVal - totalInv) / totalInv) * 100 : 0;
            const retEl = document.getElementById('totalReturn');
            retEl.innerText = UI.fmtPct(ret); retEl.className = ret >= 0 ? 'positive' : 'negative';
            App.updateCharts();
        }
    };

    const ScoringEngine = {
        parse: (val) => {
            if (val === "None" || val === "-" || val === "0" || val === 0 || val === undefined) return null;
            return parseFloat(val);
        },
        calculateVector: (data, pillars) => {
            const p = ScoringEngine.parse;
            const vec = { quality: 0, growth: 0, safety: 0, valuation: 0, trend: 0, thesis: 0, hasData: false };
            
            if(!data || !data.Symbol) return vec;
            vec.hasData = true;

            const roe = p(data.ReturnOnEquityTTM) * 100 || 0;
            const revG = p(data.QuarterlyRevenueGrowthYOY) * 100 || 0;
            const debt = data.DebtToEquityRatio === "None" ? 0 : (p(data.DebtToEquityRatio) || 0);
            const pe = p(data.PERatio) || 0;
            const price = p(data['50DayMovingAverage']) || 0;
            const ma200 = p(data['200DayMovingAverage']) || 0;

            if (roe > 20) vec.quality += 5; else if (roe > 10) vec.quality += 3;
            if (revG > 15) vec.growth += 5; else if (revG > 0) vec.growth += 2;
            if (debt < 0.5) vec.safety += 6; else if (debt < 1.0) vec.safety += 3; else vec.safety += 1;
            vec.safety += 4; 
            if (pe > 0 && pe < 25) vec.valuation = 10; else if (pe < 40) vec.valuation = 5;
            if (price > ma200) vec.trend = 1; else vec.trend = -1;

            let activePillars = pillars;
            if(!activePillars || activePillars.length === 0) {
                if(Store.profile && Store.profile.type) {
                    activePillars = InvestorTypes[Store.profile.type].pillars;
                } else {
                    activePillars = ['quality', 'value'];
                }
            }

            let matches = 0;
            if (activePillars.includes('growth') && vec.growth > 5) matches++;
            if (activePillars.includes('quality') && vec.quality > 5) matches++;
            if (activePillars.includes('safety') && vec.safety > 6) matches++;
            if (activePillars.includes('value') && vec.valuation > 5) matches++;
            
            vec.thesis = Math.max(2, Math.round((matches / (activePillars.length || 1)) * 10)); 
            
            return { vec, raw: { roe, revG, debt, pe, price, ma200 }, usedPillars: activePillars };
        },
        calculateDecision: (stock, scoreData, weight, limit) => {
            if (!scoreData.vec.hasData) return { action: "WAIT", reason: "Data Pending...", css: "bg-pending" };
            const { vec } = scoreData;
            const isOverweight = weight > limit;
            
            if (vec.thesis < 4) return { action: "EXIT", reason: "Thesis Broken", css: "bg-danger" };
            if (vec.trend < 0 && vec.valuation < 2) return { action: "REVIEW", reason: "Downtrend + Expensive", css: "bg-danger" };
            if (isOverweight && vec.thesis < 7) return { action: "TRIM", reason: "Overweight & Weakening", css: "bg-overweight" };
            if (vec.thesis >= 8 && !isOverweight && vec.trend > 0) return { action: "BUY", reason: "High Conviction Winner", css: "bg-success" };
            if (vec.thesis >= 6 && !isOverweight) return { action: "ADD", reason: "Solid Fit", css: "bg-buy-small" };
            
            return { action: "HOLD", reason: "Thesis Intact", css: "bg-success" };
        }
    };

    const App = {
        charts: { alloc: null, perf: null },
        
        init: () => {
            try {
                App.initCharts();
                UI.renderPortfolio();
                App.setupEventListeners();
                if(Store.getApiKey()) { document.getElementById('apiStatusDot').style.background = 'var(--success)'; API.fetchExchangeRate(); }
                console.log("App Initialized");
            } catch (e) { console.error(e); UI.toast("Init Failed", "error"); }
        },
        
        setupEventListeners: () => {
            document.querySelectorAll('.nav-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
                    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
                    btn.classList.add('active');
                    const tab = btn.getAttribute('data-tab');
                    document.getElementById(tab).classList.add('active');
                    if(tab === 'exit' || tab === 'buy' || tab === 'firewall') App.runExitEngine(tab);
                });
            });
            document.getElementById('refreshBtn').addEventListener('click', () => {
                if(Store.portfolio.length === 0) return UI.toast("No stocks to update", "error");
                UI.toast(`Queuing updates...`);
                Store.portfolio.forEach((s, idx) => {
                    App.updateSingleStock(idx, true);
                    API.enqueue({ function: 'OVERVIEW', symbol: s.symbol }, () => {
                        const activeTab = document.querySelector('.view.active').id;
                        if(activeTab === 'firewall' || activeTab === 'buy' || activeTab === 'exit') App.runExitEngine(activeTab);
                    });
                });
            });
            
            // --- NEW: ROBUST JSON IMPORT ---
            document.getElementById('importFile').addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (!file) return;
                const reader = new FileReader();
                reader.onload = (event) => {
                    try {
                        const json = JSON.parse(event.target.result);
                        // Handle format variations
                        const newPortfolio = Array.isArray(json) ? json : (json.portfolio || []);
                        Store.portfolio = newPortfolio;
                        // Optional: Load profile if present
                        if(json.profile) Store.profile = json.profile;
                        
                        Store.savePortfolio();
                        Store.saveProfile();
                        UI.renderPortfolio();
                        UI.toast("Portfolio Restored Successfully");
                    } catch (err) {
                        console.error(err);
                        UI.toast("Invalid JSON File", "error");
                    }
                };
                reader.readAsText(file);
                e.target.value = ''; // Reset input
            });

            // --- NEW: PDF GENERATOR ---
            document.getElementById('exportPdfBtn').addEventListener('click', () => {
                const tpl = document.getElementById('pdf-template');
                
                // Populate Template
                document.getElementById('pdfDate').innerText = new Date().toLocaleDateString();
                document.getElementById('pdfProfile').innerHTML = Store.profile ? 
                    `<strong>${InvestorTypes[Store.profile.type].name}</strong><br>${InvestorTypes[Store.profile.type].desc}` : "No Profile Set";
                
                // Populate Tables
                const pfBody = document.getElementById('pdfPortfolioBody');
                pfBody.innerHTML = '';
                Store.portfolio.forEach(s => {
                    pfBody.innerHTML += `<tr><td>${s.symbol}</td><td>${s.shares}</td><td>${UI.fmtMoney((s.currentPrice||s.price)*s.shares)}</td><td>${s.conviction}</td></tr>`;
                });

                const fwBody = document.getElementById('pdfFirewallBody');
                fwBody.innerHTML = '';
                Store.portfolio.forEach(s => {
                    const cached = Store.cache[s.symbol];
                    if(cached) {
                        const scoreData = ScoringEngine.calculateVector(cached.data, s.pillars);
                        fwBody.innerHTML += `<tr><td>${s.symbol}</td><td>${scoreData.vec.thesis}/10</td><td>${scoreData.vec.thesis>5?'Intact':'Broken'}</td></tr>`;
                    }
                });

                // Generate
                const opt = { margin: 0.5, filename: 'EquitySense_Report.pdf', image: { type: 'jpeg', quality: 0.98 }, html2canvas: { scale: 2 }, jsPDF: { unit: 'in', format: 'letter', orientation: 'portrait' } };
                html2pdf().set(opt).from(tpl).save();
            });

            // Standard Listeners (Stock Modal, Export JSON, etc.) remain...
            document.getElementById('addStockBtn').addEventListener('click', () => { 
                document.getElementById('stockForm').reset(); 
                document.getElementById('editIndex').value = ''; 
                if(Store.profile && Store.profile.type) {
                    const type = InvestorTypes[Store.profile.type];
                    if(type.pillars) type.pillars.forEach(p => { 
                        const cb = document.querySelector(`input[value="${p}"]`);
                        if(cb) cb.checked = true;
                    });
                }
                document.getElementById('stockModal').classList.add('open'); 
            });
            document.querySelectorAll('.close-modal').forEach(b => b.addEventListener('click', () => document.getElementById('stockModal').classList.remove('open')));
            document.getElementById('saveKeyBtn').addEventListener('click', () => { Store.setApiKey(document.getElementById('apiKeyInput').value); document.getElementById('apiStatusDot').style.background = 'var(--success)'; API.fetchExchangeRate(); UI.toast('Connected'); });
            
            document.getElementById('stockForm').addEventListener('submit', (e) => {
                e.preventDefault();
                const pillars = [];
                document.querySelectorAll('input[name="pillar"]:checked').forEach(cb => pillars.push(cb.value));
                const stock = { symbol: document.getElementById('mSymbol').value.toUpperCase(), shares: parseFloat(document.getElementById('mShares').value), price: parseFloat(document.getElementById('mPrice').value), conviction: document.getElementById('mConviction').value, thesis: document.getElementById('mThesis').value, pillars: pillars, currentPrice: parseFloat(document.getElementById('mPrice').value) };
                const idx = document.getElementById('editIndex').value;
                if (idx !== '') { stock.id = Store.portfolio[idx].id; stock.currentPrice = Store.portfolio[idx].currentPrice; Store.portfolio[idx] = stock; } else { stock.id = Store.generateId(); Store.portfolio.push(stock); }
                Store.savePortfolio(); UI.renderPortfolio(); document.getElementById('stockModal').classList.remove('open'); UI.toast('Saved');
            });
            document.getElementById('portfolioList').addEventListener('click', (e) => {
                const btn = e.target.closest('.action-btn');
                if(!btn) return;
                const idx = btn.getAttribute('data-index');
                if(btn.classList.contains('edit-btn')) App.editStock(idx);
                else if(btn.classList.contains('delete-btn')) App.deleteStock(btn.getAttribute('data-id'));
                else if(btn.classList.contains('refresh-btn')) App.updateSingleStock(idx);
            });
            document.getElementById('exportBtn').addEventListener('click', () => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify({ portfolio: Store.portfolio, profile: Store.profile })], {type: 'application/json'})); a.download = `portfolio_${Date.now()}.json`; a.click(); });
            
            document.getElementById('runExitScanBtn').addEventListener('click', () => App.runExitEngine('exit'));
            document.getElementById('runBuyScanBtn').addEventListener('click', () => App.runExitEngine('buy'));
            document.getElementById('runAuditBtn').addEventListener('click', () => App.runExitEngine('firewall'));
        },

        updateSingleStock: (idx, isBulk = false) => {
            const stock = Store.portfolio[idx];
            if(!isBulk) UI.toast(`Updating ${stock.symbol}...`);
            API.enqueue({ function: 'GLOBAL_QUOTE', symbol: stock.symbol }, (data) => {
                const price = parseFloat(data['Global Quote']['05. price']);
                if (price) { 
                    Store.portfolio[idx].currentPrice = price; 
                    Store.savePortfolio(); 
                    UI.renderPortfolio(); 
                    if(!isBulk) document.getElementById('lastUpdated').innerText = `Updated ${stock.symbol} at ${new Date().toLocaleTimeString()}`;
                }
            });
        },

        runExitEngine: (mode, filter = 'all') => {
            const gridId = mode === 'buy' ? 'buyGrid' : (mode === 'firewall' ? 'firewallGrid' : 'exitGrid');
            const grid = document.getElementById(gridId);
            grid.innerHTML = '';
            
            let count = 0;
            const totalVal = Store.portfolio.reduce((acc,s) => acc + (s.currentPrice * s.shares), 0);
            const limit = getRebalanceLimits(Store.profile?.type).max;

            Store.portfolio.forEach(stock => {
                const cached = Store.cache[stock.symbol];
                if(cached) {
                    const scoreData = ScoringEngine.calculateVector(cached.data, stock.pillars || []);
                    const weight = ((stock.currentPrice * stock.shares) / totalVal);
                    
                    const decision = ScoringEngine.calculateDecision(stock, scoreData, weight, limit);
                    
                    if (mode === 'exit' && (decision.action === 'HOLD' || decision.action === 'BUY' || decision.action === 'ADD' || decision.action === 'WAIT')) return;
                    if (mode === 'buy' && (decision.action !== 'BUY' && decision.action !== 'ADD')) return;
                    if (mode === 'firewall') {
                        if(filter === 'actionable' && decision.action === 'HOLD') return;
                        if(filter === 'warning' && (decision.action === 'BUY' || decision.action === 'ADD')) return;
                    }
                    
                    const card = document.createElement('div');
                    card.className = 'audit-card';
                    card.innerHTML = `<div class="action-banner ${decision.css} text-white">${decision.action}</div><div class="audit-header"><div><strong>${stock.symbol}</strong><br><small>Alloc: ${(weight*100).toFixed(1)}%</small></div><div class="score-badge ${decision.css}">${scoreData.vec.thesis}/10</div></div><div class="audit-body"><p class="health-reason">${decision.reason}</p><div class="vector-row"><div class="vector-label">Thesis</div><div class="vector-track"><div class="vector-fill ${scoreData.vec.thesis>6?'bg-success':'bg-danger'}" style="width:${scoreData.vec.thesis*10}%"></div></div></div></div>`;
                    grid.appendChild(card);
                    count++;
                }
            });
            if(count === 0) grid.innerHTML = '<div class="empty-state">No signals found.</div>';
        },

        editStock: (idx) => {
            const s = Store.portfolio[idx];
            document.getElementById('mSymbol').value = s.symbol;
            document.getElementById('mShares').value = s.shares;
            document.getElementById('mPrice').value = s.price;
            document.getElementById('mConviction').value = s.conviction;
            document.getElementById('mThesis').value = s.thesis || "";
            document.getElementById('editIndex').value = idx;
            if(s.pillars) s.pillars.forEach(p => { const cb = document.querySelector(`input[value="${p}"]`); if(cb) cb.checked = true; });
            document.getElementById('stockModal').classList.add('open');
        },
        deleteStock: (id) => { if(confirm('Delete?')) { Store.portfolio = Store.portfolio.filter(s => s.id !== id); Store.savePortfolio(); UI.renderPortfolio(); }},

        initCharts: () => {
            const ctx1 = document.getElementById('allocationChart'), ctx2 = document.getElementById('performanceChart');
            const commonOpts = { responsive: true, maintainAspectRatio: false };
            if(ctx1) App.charts.alloc = new Chart(ctx1, { type: 'doughnut', data: { labels: [], datasets: [{ data: [], backgroundColor: [] }] }, options: commonOpts });
            if(ctx2) App.charts.perf = new Chart(ctx2, { type: 'bar', data: { labels: [], datasets: [{ label: 'Return %', data: [], backgroundColor: [] }] }, options: { ...commonOpts, scales: { x: { display: false }, y: { grid: { color: '#334155' } } } } });
        },
        updateCharts: () => {
            if(!App.charts.alloc) return;
            const labels = Store.portfolio.map(s => s.symbol);
            const data = Store.portfolio.map(s => (s.currentPrice ? parseFloat(s.currentPrice) : parseFloat(s.price)) * parseFloat(s.shares));
            const count = Store.portfolio.length;
            const colors = Array.from({length: count}, (_, i) => `hsl(${i * (360 / count)}, 65%, 55%)`);
            App.charts.alloc.data.labels = labels; App.charts.alloc.data.datasets[0].data = data; App.charts.alloc.data.datasets[0].backgroundColor = colors; App.charts.alloc.update();
            App.charts.perf.data.labels = labels;
            App.charts.perf.data.datasets[0].data = Store.portfolio.map(s => { const cost = parseFloat(s.price) * parseFloat(s.shares); const curr = (s.currentPrice ? parseFloat(s.currentPrice) : parseFloat(s.price)) * parseFloat(s.shares); return ((curr - cost) / cost) * 100; });
            App.charts.perf.data.datasets[0].backgroundColor = App.charts.perf.data.datasets[0].data.map(v => v >= 0 ? '#22c55e' : '#ef4444');
            App.charts.perf.update();
        }
    };
    App.init();
});