document.addEventListener('DOMContentLoaded', () => {
    console.log("System initializing...");

    // --- STATE MANAGEMENT ---
    const Store = {
        portfolio: JSON.parse(localStorage.getItem('ep_portfolio')) || [],
        settings: JSON.parse(localStorage.getItem('ep_settings')) || { currency: 'USD' },
        // Profile is now an object with behavior parameters
        profile: JSON.parse(localStorage.getItem('ep_profile')) || null,
        auditLog: JSON.parse(localStorage.getItem('ep_audit')) || [],
        cache: JSON.parse(localStorage.getItem('ep_cache')) || {},
        exchangeRate: 1.0,
        
        getApiKey: () => sessionStorage.getItem('ep_api_key'),
        setApiKey: (key) => sessionStorage.setItem('ep_api_key', key),
        savePortfolio: () => localStorage.setItem('ep_portfolio', JSON.stringify(Store.portfolio)),
        saveProfile: () => localStorage.setItem('ep_profile', JSON.stringify(Store.profile)),
        saveAudit: () => localStorage.setItem('ep_audit', JSON.stringify(Store.auditLog)),
        saveCache: () => localStorage.setItem('ep_cache', JSON.stringify(Store.cache)),
        saveSettings: () => localStorage.setItem('ep_settings', JSON.stringify(Store.settings)),
        generateId: () => '_' + Math.random().toString(36).substr(2, 9)
    };

    // --- SCORING ENGINE (VECTOR) ---
    const ScoringEngine = {
        parse: (val) => {
            if (val === "None" || val === "-" || val === "0" || val === 0) return 0;
            return parseFloat(val) || 0;
        },
        // Returns a Vector of scores (0-10) instead of single number
        calculateVector: (data, pillars) => {
            const p = ScoringEngine.parse;
            const vec = { quality: 0, growth: 0, safety: 0, valuation: 0, trend: 0, thesis: 0 };
            
            // Raw Metrics
            const roe = p(data.ReturnOnEquityTTM) * 100;
            const opMargin = p(data.OperatingMarginTTM) * 100;
            const revG = p(data.QuarterlyRevenueGrowthYOY) * 100;
            const epsG = p(data.QuarterlyEarningsGrowthYOY) * 100;
            const debt = data.DebtToEquityRatio === "None" ? 0 : p(data.DebtToEquityRatio);
            const pe = p(data.PERatio);
            const price = p(data['50DayMovingAverage']);
            const ma200 = p(data['200DayMovingAverage']);

            // 1. Quality (0-10)
            if (roe > 20) vec.quality += 5; else if (roe > 10) vec.quality += 3;
            if (opMargin > 20) vec.quality += 5; else if (opMargin > 10) vec.quality += 3;

            // 2. Growth (0-10)
            if (revG > 15) vec.growth += 5; else if (revG > 0) vec.growth += 2;
            if (epsG > 15) vec.growth += 5; else if (epsG > 0) vec.growth += 2;

            // 3. Safety (0-10)
            if (debt < 0.5) vec.safety += 6; else if (debt < 1.0) vec.safety += 3;
            // Quick ratio or current ratio proxies could be added here from Balance Sheet if available
            // For now, assuming decent liquidity if debt is low.
            vec.safety += 4; // Baseline assumption for non-bankrupt firms

            // 4. Valuation (0-10) (Inverted: Lower PE is better)
            if (pe > 0) {
                if (pe < 15) vec.valuation = 10;
                else if (pe < 25) vec.valuation = 7;
                else if (pe < 40) vec.valuation = 4;
                else vec.valuation = 1;
            }

            // 5. Trend (Risk Modifier)
            if (price > ma200) vec.trend = 1; // Bullish context
            else vec.trend = -1; // Bearish context

            // 6. Thesis Check (Does it match pillars?)
            let thesisMatches = 0;
            if (pillars.includes('growth') && vec.growth > 6) thesisMatches++;
            if (pillars.includes('quality') && vec.quality > 6) thesisMatches++;
            if (pillars.includes('safety') && vec.safety > 6) thesisMatches++;
            if (pillars.includes('value') && vec.valuation > 6) thesisMatches++;
            
            // Normalize Thesis Score (0-10)
            const pillarCount = pillars.length || 1;
            vec.thesis = Math.min(10, Math.round((thesisMatches / pillarCount) * 10));

            return vec;
        }
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
                // Cache OVERVIEW
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
            if (!key) throw new Error("Missing Key");
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
            let val = n;
            let code = 'USD';
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
                
                totalInv += cost;
                totalVal += val;

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td style="font-weight:700; font-family: var(--font-mono)">${stock.symbol}</td>
                    <td>${sShares}</td>
                    <td>${UI.fmtMoney(sPrice)}</td>
                    <td style="color:${stock.currentPrice ? '' : 'var(--text-secondary)'}">${stock.currentPrice ? UI.fmtMoney(sCurr) : 'Pending...'}</td>
                    <td>${UI.fmtMoney(val)}</td>
                    <td class="${ret > 0 ? 'positive' : (ret < 0 ? 'negative' : '')}">${UI.fmtPct(ret)}</td>
                    <td>${stock.conviction}</td>
                    <td>
                        <button class="btn-icon action-btn refresh-btn" data-index="${idx}" title="Update Price"><i class="fa-solid fa-rotate"></i></button>
                        <button class="btn-icon action-btn edit-btn" data-index="${idx}" title="Edit"><i class="fa-solid fa-pen"></i></button>
                        <button class="btn-icon action-btn delete-btn" data-id="${stock.id}" style="color:var(--danger)" title="Delete"><i class="fa-solid fa-trash"></i></button>
                    </td>
                `;
                tbody.appendChild(tr);
            });

            document.getElementById('totalInvested').innerText = UI.fmtMoney(totalInv);
            document.getElementById('totalValue').innerText = UI.fmtMoney(totalVal);
            const ret = totalInv > 0 ? ((totalVal - totalInv) / totalInv) * 100 : 0;
            const retEl = document.getElementById('totalReturn');
            retEl.innerText = UI.fmtPct(ret);
            retEl.className = ret >= 0 ? 'positive' : 'negative';
            
            App.updateCharts();
        }
    };

    const ProfileEngine = {
        // Defaults: Neutral Value Investor
        defaultParams: {
            name: "Neutral Value (Default)",
            maxAlloc: 0.15,
            riskTolerance: "moderate",
            pillars: ['value', 'quality'] 
        },

        init: () => {
            // Check if profile exists, if not use default but don't save it yet (allow quiz)
            const activeProfile = Store.profile || ProfileEngine.defaultParams;
            ProfileEngine.renderDashboard(activeProfile);
            
            document.getElementById('submitQuizBtn').addEventListener('click', ProfileEngine.processQuiz);
            document.getElementById('retakeQuizBtn').addEventListener('click', () => {
                document.getElementById('quizView').classList.remove('hidden');
                document.getElementById('profileDashboard').classList.add('hidden');
                document.getElementById('retakeQuizBtn').classList.add('hidden');
            });
            document.getElementById('runHealthCheckBtn').addEventListener('click', ProfileEngine.runHealthCheck);
        },

        processQuiz: () => {
            // Behavioral mapping
            const q = (i) => document.getElementById(`q${i}`).value;
            let params = { name: "Custom Profile", maxAlloc: 0.15, pillars: [] };
            
            // Map Q1 (Goal) -> Base Name
            if(q(0) === 'growth') params.name = "Long-Term Compounder";
            if(q(0) === 'income') { params.name = "Income Specialist"; params.pillars.push('safety'); }
            if(q(0) === 'safety') { params.name = "Risk Minimizer"; params.maxAlloc = 0.10; params.pillars.push('safety'); }
            
            // Map Q6 (Concentration) -> Max Alloc
            if(q(5) === 'high') params.maxAlloc = 0.25;
            if(q(5) === 'diversified') params.maxAlloc = 0.08;

            // Map Q5 (Metrics) -> Pillars
            if(q(4) === 'quality') params.pillars.push('quality');
            if(q(4) === 'value') params.pillars.push('value');
            if(q(4) === 'trend') params.pillars.push('growth'); // Use growth as proxy for trend momentum fundies

            // Dedupe pillars
            params.pillars = [...new Set(params.pillars)];
            if(params.pillars.length === 0) params.pillars = ['quality', 'value']; // Fallback

            Store.profile = params;
            Store.saveProfile();
            UI.toast("Profile Calibrated");
            ProfileEngine.renderDashboard(params);
        },

        renderDashboard: (p) => {
            document.getElementById('quizView').classList.add('hidden');
            document.getElementById('profileDashboard').classList.remove('hidden');
            document.getElementById('retakeQuizBtn').classList.remove('hidden');
            
            document.getElementById('profileTypeName').innerText = p.name;
            document.getElementById('profileTypeDesc').innerText = `Max Position: ${(p.maxAlloc*100)}% | Key Pillars: ${p.pillars.join(', ')}`;
            
            // Render Audit Log
            const ul = document.getElementById('auditLogList');
            ul.innerHTML = '';
            if(Store.auditLog.length === 0) ul.innerHTML = '<li>No actions recorded yet.</li>';
            else {
                Store.auditLog.slice().reverse().forEach(log => {
                    const li = document.createElement('li');
                    li.innerHTML = `<strong>${log.date}</strong> - ${log.action.toUpperCase()} ${log.symbol}: ${log.reason}`;
                    ul.appendChild(li);
                });
            }
        },

        runHealthCheck: () => {
            // System Level Health Logic
            let brokenCap = 0;
            let totalCap = 0;
            let maxConc = 0;

            const grid = document.getElementById('healthGrid');
            grid.innerHTML = '';

            if(Store.portfolio.length === 0) {
                grid.innerHTML = '<div class="empty-state">No stocks to analyze.</div>';
                return;
            }

            Store.portfolio.forEach(stock => {
                const val = (stock.currentPrice || stock.price) * stock.shares;
                totalCap += val;
                
                const cached = Store.cache[stock.symbol];
                if(cached) {
                    const vec = ScoringEngine.calculateVector(cached.data, stock.pillars || Store.profile?.pillars || []);
                    if(vec.thesis < 5) brokenCap += val; // Thesis broken
                    
                    // Render Mini Card
                    const card = document.createElement('div');
                    card.className = 'audit-card';
                    card.innerHTML = `
                        <div class="audit-header"><strong>${stock.symbol}</strong><div class="score-badge ${vec.thesis>6?'bg-success':'bg-danger'}">${vec.thesis}/10</div></div>
                        <div class="audit-body">
                            <div class="vector-row"><div class="vector-label">Quality</div><div class="vector-track"><div class="vector-fill bg-success" style="width:${vec.quality*10}%"></div></div></div>
                            <div class="vector-row"><div class="vector-label">Growth</div><div class="vector-track"><div class="vector-fill bg-warning" style="width:${vec.growth*10}%"></div></div></div>
                            <div class="vector-row"><div class="vector-label">Safety</div><div class="vector-track"><div class="vector-fill bg-buy-small" style="width:${vec.safety*10}%"></div></div></div>
                        </div>
                    `;
                    grid.appendChild(card);
                }
            });

            // Calculate System Metrics
            if (totalCap > 0) {
                // Find max concentration
                Store.portfolio.forEach(s => {
                    const v = (s.currentPrice || s.price) * s.shares;
                    const w = v / totalCap;
                    if(w > maxConc) maxConc = w;
                });

                document.getElementById('sysConcRisk').innerText = (maxConc*100).toFixed(1) + "%";
                document.getElementById('sysBrokenCap').innerText = ((brokenCap/totalCap)*100).toFixed(1) + "%";
                
                let grade = "A";
                if(brokenCap/totalCap > 0.2) grade = "B";
                if(brokenCap/totalCap > 0.4) grade = "C";
                if(maxConc > (Store.profile?.maxAlloc || 0.15) * 1.5) grade = "D"; // Extreme concentration
                
                const gEl = document.getElementById('sysHealthGrade');
                gEl.innerText = grade;
                gEl.className = `grade-badge grade-${grade}`;
            }
        }
    };

    const App = {
        charts: { alloc: null, perf: null },

        init: () => {
            try {
                App.initCharts();
                UI.renderPortfolio();
                App.setupEventListeners();
                ProfileEngine.init();
                
                document.getElementById('currencySwitch').checked = (Store.settings.currency === 'EUR');
                document.getElementById('currLabel').innerText = Store.settings.currency === 'EUR' ? 'EUR' : 'USD';
                
                if(Store.getApiKey()) {
                    document.getElementById('apiStatusDot').style.background = 'var(--success)';
                    API.fetchExchangeRate();
                }
                console.log("App Initialized");
            } catch (e) { console.error(e); UI.toast("Init Failed", "error"); }
        },
        
        setupEventListeners: () => {
            // Tab Nav
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

            // Update Logic
            document.getElementById('refreshBtn').addEventListener('click', () => {
                if(Store.portfolio.length === 0) return UI.toast("No stocks to update", "error");
                UI.toast(`Queuing updates...`);
                Store.portfolio.forEach((s, idx) => {
                    App.updateSingleStock(idx, true);
                    API.enqueue({ function: 'OVERVIEW', symbol: s.symbol }, () => {
                        // Refresh logic handled by cache checks on tab switch
                    });
                });
            });

            // Buttons
            document.getElementById('currencySwitch').addEventListener('change', (e) => { Store.settings.currency = e.target.checked ? 'EUR' : 'USD'; Store.saveSettings(); document.getElementById('currLabel').innerText = Store.settings.currency === 'EUR' ? 'EUR' : 'USD'; UI.renderPortfolio(); });
            document.getElementById('exportPdfBtn').addEventListener('click', () => { const element = document.getElementById('reportContent'); html2pdf().set({ margin:0.5, filename:'EquitySense.pdf', image:{type:'jpeg',quality:0.98}, html2canvas:{scale:2}, jsPDF:{unit:'in',format:'letter',orientation:'portrait'} }).from(element).save(); });
            
            // Modals
            const stockModal = document.getElementById('stockModal');
            const exitModal = document.getElementById('exitReasonModal');
            
            document.getElementById('addStockBtn').addEventListener('click', () => { 
                document.getElementById('stockForm').reset(); document.getElementById('editIndex').value = ''; 
                // Smart Auto-Fill Thesis Pillars based on Profile
                if(Store.profile && Store.profile.pillars) {
                    Store.profile.pillars.forEach(p => {
                        const cb = document.querySelector(`input[value="${p}"]`);
                        if(cb) cb.checked = true;
                    });
                }
                stockModal.classList.add('open'); 
            });
            
            document.querySelectorAll('.close-modal').forEach(b => b.addEventListener('click', () => stockModal.classList.remove('open')));
            document.querySelectorAll('.close-modal-exit').forEach(b => b.addEventListener('click', () => exitModal.classList.remove('open')));
            
            document.getElementById('saveKeyBtn').addEventListener('click', () => { Store.setApiKey(document.getElementById('apiKeyInput').value); document.getElementById('apiStatusDot').style.background = 'var(--success)'; API.fetchExchangeRate(); UI.toast('API Key Connected'); });
            
            document.getElementById('stockForm').addEventListener('submit', (e) => {
                e.preventDefault();
                const pillars = [];
                document.querySelectorAll('input[name="pillar"]:checked').forEach(cb => pillars.push(cb.value));
                const stock = { symbol: document.getElementById('mSymbol').value.toUpperCase(), shares: parseFloat(document.getElementById('mShares').value), price: parseFloat(document.getElementById('mPrice').value), conviction: document.getElementById('mConviction').value, thesis: document.getElementById('mThesis').value, pillars: pillars, currentPrice: parseFloat(document.getElementById('mPrice').value) };
                const idx = document.getElementById('editIndex').value;
                if (idx !== '') { stock.id = Store.portfolio[idx].id; stock.currentPrice = Store.portfolio[idx].currentPrice; Store.portfolio[idx] = stock; } else { stock.id = Store.generateId(); Store.portfolio.push(stock); }
                Store.savePortfolio(); UI.renderPortfolio(); stockModal.classList.remove('open'); UI.toast('Portfolio Updated');
            });

            // EXIT FORM SUBMIT
            document.getElementById('exitForm').addEventListener('submit', (e) => {
                e.preventDefault();
                const id = document.getElementById('exitStockId').value;
                const reason = document.getElementById('exitReason').value;
                const action = document.getElementById('exitActionType').value;
                
                const stockIndex = Store.portfolio.findIndex(s => s.id === id);
                if (stockIndex === -1) return;
                const stock = Store.portfolio[stockIndex];

                // Log to Audit Trail
                const logEntry = {
                    date: new Date().toLocaleDateString(),
                    symbol: stock.symbol,
                    action: action,
                    reason: reason
                };
                Store.auditLog.push(logEntry);
                Store.saveAudit();

                // Perform Action
                if (action === 'exit') {
                    Store.portfolio.splice(stockIndex, 1);
                } else {
                    // Trim Logic (Simplified: Reduce shares by 50% for now)
                    Store.portfolio[stockIndex].shares = stock.shares * 0.5;
                }
                
                Store.savePortfolio();
                UI.renderPortfolio();
                exitModal.classList.remove('open');
                UI.toast(`Position ${action === 'exit' ? 'Exited' : 'Trimmed'}`);
            });

            document.getElementById('portfolioList').addEventListener('click', (e) => {
                const btn = e.target.closest('.action-btn');
                if(!btn) return;
                const idx = btn.getAttribute('data-index');
                if(btn.classList.contains('edit-btn')) App.editStock(idx);
                else if(btn.classList.contains('delete-btn')) App.triggerExitFlow(btn.getAttribute('data-id')); // Trigger Exit Flow
                else if(btn.classList.contains('refresh-btn')) App.updateSingleStock(idx);
            });
            
            // Scan Buttons
            document.getElementById('runExitScanBtn').addEventListener('click', () => App.runExitEngine('exit'));
            document.getElementById('runAuditBtn').addEventListener('click', () => App.runExitEngine('firewall'));
            // Export
            document.getElementById('exportBtn').addEventListener('click', () => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify({ portfolio: Store.portfolio })], {type: 'application/json'})); a.download = `portfolio_${Date.now()}.json`; a.click(); });
            const handleImp = (e, replace) => { const reader = new FileReader(); reader.onload = (ev) => { try { Store.portfolio = replace ? JSON.parse(ev.target.result).portfolio : [...Store.portfolio, ...JSON.parse(ev.target.result).portfolio]; Store.savePortfolio(); UI.renderPortfolio(); UI.toast("Import Successful"); } catch(err) { UI.toast("Import Failed", "error"); } }; if(e.target.files.length > 0) reader.readAsText(e.target.files[0]); };
            document.getElementById('importMerge').onchange = (e) => handleImp(e, false); document.getElementById('importReplace').onchange = (e) => handleImp(e, true);
        },

        triggerExitFlow: (id) => {
            document.getElementById('exitStockId').value = id;
            document.getElementById('exitReasonModal').classList.add('open');
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

        // EXIT STRATEGY ENGINE
        runExitEngine: (mode) => {
            const gridId = mode === 'buy' ? 'buyGrid' : (mode === 'firewall' ? 'firewallGrid' : 'exitGrid');
            const grid = document.getElementById(gridId);
            grid.innerHTML = '';
            
            // Progressive Disclosure: Check if user has enough stocks
            if (mode === 'exit' && Store.portfolio.length < 3) {
                document.getElementById('exitLocked').classList.remove('hidden');
                grid.style.display = 'none';
                return;
            }
            if (mode === 'exit') {
                document.getElementById('exitLocked').classList.add('hidden');
                grid.style.display = 'grid';
            }

            // Calculate Portfolio Total for Weighting
            const totalVal = Store.portfolio.reduce((acc,s) => acc + (s.currentPrice * s.shares), 0);
            const maxAlloc = Store.profile ? Store.profile.maxAlloc : 0.15;

            Store.portfolio.forEach(stock => {
                const cached = Store.cache[stock.symbol];
                if(cached) {
                    const vec = ScoringEngine.calculateVector(cached.data, stock.pillars || Store.profile?.pillars || []);
                    const weight = ((stock.currentPrice * stock.shares) / totalVal);
                    
                    // Logic Engine
                    let action = "HOLD";
                    let confidence = "High";
                    let reason = "Thesis intact.";
                    let css = "bg-success";

                    if (mode === 'exit') {
                        // 1. Check Thesis
                        if (vec.thesis < 5) { action = "EXIT"; reason = "Thesis Pillars Broken (Growth/Metrics mismatch)"; css = "bg-danger"; }
                        // 2. Check Risk
                        else if (weight > maxAlloc) { action = "TRIM"; reason = `Overweight (${(weight*100).toFixed(1)}% > ${(maxAlloc*100)}%)`; css = "bg-overweight"; }
                        // 3. Check Trend Risk
                        else if (vec.trend < 0 && vec.valuation < 4) { action = "WATCH"; reason = "Downtrend + Expensive"; css = "bg-warning"; }
                        
                        if (action === "HOLD") return; // Don't show holds in Exit tab
                    } 
                    else if (mode === 'firewall') {
                        // Firewall shows everything
                        if (vec.thesis < 5) { action="BROKEN"; css="bg-danger"; }
                        else if (vec.thesis < 8) { action="WEAK"; css="bg-warning"; }
                        else { action="INTACT"; css="bg-success"; }
                        reason = `Vector Score: Quality ${vec.quality}, Growth ${vec.growth}`;
                    }
                    
                    // Render Logic
                    const card = document.createElement('div');
                    card.className = 'audit-card';
                    card.innerHTML = `
                        <div class="action-banner ${css} text-white">${action}</div>
                        <div class="audit-header"><strong>${stock.symbol}</strong><small>${(weight*100).toFixed(1)}% Alloc</small></div>
                        <div class="audit-body"><p class="health-reason">${reason}</p>
                        <div class="vector-row"><div class="vector-label">Thesis</div><div class="vector-track"><div class="vector-fill ${vec.thesis>6?'bg-success':'bg-danger'}" style="width:${vec.thesis*10}%"></div></div></div>
                        </div>
                    `;
                    grid.appendChild(card);
                }
            });
            if(grid.innerHTML === '') grid.innerHTML = '<div class="empty-state">No signals found.</div>';
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

            App.charts.alloc.data.labels = labels;
            App.charts.alloc.data.datasets[0].data = data;
            App.charts.alloc.data.datasets[0].backgroundColor = colors;
            App.charts.alloc.update();

            App.charts.perf.data.labels = labels;
            App.charts.perf.data.datasets[0].data = Store.portfolio.map(s => { 
                const cost = parseFloat(s.price) * parseFloat(s.shares); 
                const curr = (s.currentPrice ? parseFloat(s.currentPrice) : parseFloat(s.price)) * parseFloat(s.shares); 
                return ((curr - cost) / cost) * 100; 
            });
            App.charts.perf.data.datasets[0].backgroundColor = App.charts.perf.data.datasets[0].data.map(v => v >= 0 ? '#22c55e' : '#ef4444');
            App.charts.perf.update();
        }
    };
    App.init();
});