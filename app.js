document.addEventListener('DOMContentLoaded', () => {
    console.log("System initializing...");

    // --- STATE MANAGEMENT ---
    const Store = {
        portfolio: JSON.parse(localStorage.getItem('ep_portfolio')) || [],
        settings: JSON.parse(localStorage.getItem('ep_settings')) || {},
        profile: JSON.parse(localStorage.getItem('ep_profile')) || null,
        cache: JSON.parse(localStorage.getItem('ep_cache')) || {},
        
        getApiKey: () => sessionStorage.getItem('ep_api_key'),
        setApiKey: (key) => sessionStorage.setItem('ep_api_key', key),
        savePortfolio: () => localStorage.setItem('ep_portfolio', JSON.stringify(Store.portfolio)),
        saveProfile: () => localStorage.setItem('ep_profile', JSON.stringify(Store.profile)),
        saveCache: () => localStorage.setItem('ep_cache', JSON.stringify(Store.cache)),
        generateId: () => '_' + Math.random().toString(36).substr(2, 9)
    };

    const InvestorTypes = {
        "Compounder": { id: 1, name: "Long-Term Compounder", desc: "Maximizes long-term intrinsic value.", weights: { growth: 0.4, quality: 0.4, safety: 0.1, value: 0.1 } },
        "Redeployer": { id: 2, name: "Capital Redeployer", desc: "Reallocates capital to best opportunities.", weights: { value: 0.4, momentum: 0.2, growth: 0.2, safety: 0.2 } },
        "CashConstrained": { id: 3, name: "Cash-Constrained", desc: "Grows capital with limited surplus.", weights: { safety: 0.5, value: 0.3, quality: 0.2, growth: 0.0 } },
        "Income": { id: 4, name: "Income-Focused", desc: "Prioritizes stable cash flows.", weights: { dividend: 0.5, safety: 0.3, quality: 0.2, growth: 0.0 } },
        "RiskMinimizer": { id: 5, name: "Risk-Minimizer", desc: "Capital preservation is paramount.", weights: { safety: 0.6, quality: 0.3, value: 0.1, growth: 0.0 } },
        "DrawdownSensitive": { id: 6, name: "Drawdown-Sensitive", desc: "Strict loss limits.", weights: { safety: 0.5, momentum: 0.2, quality: 0.3, growth: 0.0 } },
        "TimeHorizon": { id: 7, name: "Time-Horizon Optimizer", desc: "Maximizes capital for future date.", weights: { growth: 0.5, quality: 0.3, value: 0.2, safety: 0.0 } },
        "VolatilityAgnostic": { id: 8, name: "Volatility-Agnostic", desc: "CAGR above all else.", weights: { growth: 0.6, momentum: 0.2, value: 0.2, safety: 0.0 } },
        "LiquidityConstrained": { id: 9, name: "Liquidity-Constrained", desc: "Needs near-term access to cash.", weights: { safety: 0.4, quality: 0.4, momentum: 0.2, growth: 0.0 } },
        "Concentrator": { id: 10, name: "Conviction-Weighted", desc: "Outsized returns via few bets.", weights: { quality: 0.5, growth: 0.3, value: 0.2, safety: 0.0 } },
        "Stabilizer": { id: 11, name: "Diversification-First", desc: "Reduces idiosyncratic risk.", weights: { safety: 0.4, quality: 0.4, value: 0.2, growth: 0.0 } },
        "ValuationAnchored": { id: 12, name: "Valuation-Anchored", desc: "Only buys with Margin of Safety.", weights: { value: 0.7, quality: 0.2, safety: 0.1, growth: 0.0 } },
        "Systematic": { id: 13, name: "Rule-Bound Systematic", desc: "Strict adherence to rules.", weights: { quality: 0.3, value: 0.3, safety: 0.3, growth: 0.1 } },
        "CycleTimer": { id: 14, name: "Opportunistic Cycle-Timer", desc: "Exploits market cycles.", weights: { value: 0.4, momentum: 0.4, quality: 0.2, safety: 0.0 } },
        "PreservationPlus": { id: 15, name: "Capital-Preservation-Plus", desc: "Beat inflation, low risk.", weights: { safety: 0.7, quality: 0.2, dividend: 0.1, growth: 0.0 } }
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
        enqueue: (params, callback, errorCallback) => {
            API.queue.push({ params, callback, errorCallback });
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
                    if(task.params.function === 'OVERVIEW' && !data.Note) {
                        Store.cache[task.params.symbol] = { data: data, ts: Date.now() };
                        Store.saveCache();
                    }
                }
                task.callback(data);
            } catch (err) {
                if(task.errorCallback) task.errorCallback(err);
                UI.toast(`API Error: ${err.message}`, 'error');
            }
            let countdown = 150; 
            const timer = setInterval(() => {
                countdown--;
                UI.updateProgress((150 - countdown) / 150 * 100);
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
            const data = await res.json();
            if (data.Note) throw new Error("API Limit Reached");
            if (data['Error Message']) throw new Error("Invalid Ticker/Data");
            return data;
        }
    };

    const UI = {
        toast: (msg, type = 'info') => {
            const el = document.createElement('div');
            el.className = 'toast';
            el.style.borderLeftColor = type === 'error' ? 'var(--danger)' : 'var(--success)';
            el.innerText = msg;
            document.getElementById('toastContainer').appendChild(el);
            setTimeout(() => el.remove(), 4000);
        },
        updateQueue: (count, active = false) => {
            const lbl = document.getElementById('apiQueueLabel');
            if(lbl) lbl.innerText = active ? `Processing... (${count} pending)` : 'Queue: Idle';
        },
        updateProgress: (pct) => {
            const bar = document.getElementById('apiProgressBar');
            if(bar) bar.style.width = `${pct}%`;
        },
        fmtMoney: (n) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n),
        fmtPct: (n) => `${(n).toFixed(2)}%`,
        
        renderPortfolio: () => {
            const tbody = document.getElementById('portfolioList');
            if (!tbody) return;
            tbody.innerHTML = '';
            let totalInv = 0, totalVal = 0;

            Store.portfolio.forEach((stock, idx) => {
                // Ensure numbers
                const sShares = parseFloat(stock.shares);
                const sPrice = parseFloat(stock.price);
                const sCurr = stock.currentPrice ? parseFloat(stock.currentPrice) : sPrice;

                const val = sCurr * sShares;
                const cost = sPrice * sShares;
                
                let ret = 0;
                if(sCurr && sCurr !== sPrice) {
                     ret = ((val - cost) / cost) * 100;
                }
                
                totalInv += cost;
                totalVal += val;

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td style="font-weight:700; font-family: var(--font-mono)">${stock.symbol}</td>
                    <td>${sShares}</td>
                    <td>${UI.fmtMoney(sPrice)}</td>
                    <td style="color:${stock.currentPrice ? '' : 'var(--text-secondary)'}">
                        ${stock.currentPrice ? UI.fmtMoney(sCurr) : 'Pending...'}
                    </td>
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

    const ScoringEngine = {
        parse: (val) => {
            if (val === "None" || val === "-" || val === "0" || val === 0) return 0;
            return parseFloat(val) || 0;
        },
        calculate: (data) => {
            const p = ScoringEngine.parse;
            const raw = {
                revG: (p(data.QuarterlyRevenueGrowthYOY) * 100).toFixed(1),
                epsG: (p(data.QuarterlyEarningsGrowthYOY) * 100).toFixed(1),
                roe: (p(data.ReturnOnEquityTTM) * 100).toFixed(1),
                margin: (p(data.OperatingMarginTTM) * 100).toFixed(1),
                debt: data.DebtToEquityRatio === "None" ? 0 : p(data.DebtToEquityRatio),
                ma200: p(data['200DayMovingAverage']),
                price: p(data['50DayMovingAverage'])
            };
            let score = 0;
            if (p(raw.revG) > 10) score += 15; else if (p(raw.revG) > 0) score += 10;
            if (p(raw.epsG) > 10) score += 15; else if (p(raw.epsG) > 0) score += 5;
            if (p(raw.roe) > 15) score += 15; else if (p(raw.roe) > 8) score += 10;
            if (p(raw.margin) > 20) score += 15; else if (p(raw.margin) > 10) score += 10;
            if (raw.debt < 0.5) score += 20; else if (raw.debt < 1.0) score += 10;
            if (raw.price > raw.ma200) score += 20;
            return { score, raw };
        }
    };

    const ProfileEngine = {
        init: () => {
            if (Store.profile) {
                ProfileEngine.renderDashboard();
            } else {
                ProfileEngine.renderQuiz();
            }
            document.getElementById('submitQuizBtn').addEventListener('click', ProfileEngine.processQuiz);
            document.getElementById('retakeQuizBtn').addEventListener('click', () => {
                Store.profile = null;
                Store.saveProfile();
                ProfileEngine.renderQuiz();
            });
            document.getElementById('runHealthCheckBtn').addEventListener('click', ProfileEngine.runHealthCheck);
            document.querySelectorAll('.goto-profile-btn').forEach(b => b.addEventListener('click', () => {
                document.querySelector('.nav-btn[data-tab="profile"]').click();
            }));
        },
        renderQuiz: () => {
            document.getElementById('quizView').classList.remove('hidden');
            document.getElementById('profileDashboard').classList.add('hidden');
            document.getElementById('retakeQuizBtn').classList.add('hidden');
            const qs = [
                { l: "1. Primary Goal?", o: [["growth","Multi-Generational Wealth"], ["income","Steady Passive Income"], ["safety","Capital Preservation"], ["trend","Beating the Market"]] },
                { l: "2. Market Crash (-30%) Reaction?", o: [["buy","Buy Aggressively"], ["hold","Do Nothing"], ["check","Re-evaluate Thesis"], ["sell","Sell to Protect"]] },
                { l: "3. Liquidity Needs?", o: [["none","Locked for 10+ Years"], ["low","Might need in 3-5 Years"], ["high","Need access < 1 Year"]] },
                { l: "4. Management Style?", o: [["active","Daily/Weekly"], ["passive","Quarterly/Yearly"]] },
                { l: "5. Metric Focus?", o: [["quality","ROE & Margins"], ["value","P/E & Free Cash Flow"], ["trend","Price Momentum"], ["safety","Debt & Assets"]] },
                { l: "6. Concentration?", o: [["high","Top 5 stocks = 50%"], ["balanced","10-20 Stocks"], ["diversified","30+ Stocks"]] },
                { l: "7. Volatility?", o: [["love","Opportunity to buy"], ["ignore","Noise"], ["hate","Stressful"]] },
                { l: "8. Profit Taking?", o: [["never","Hold Forever"], ["valuation","Trim when expensive"], ["target","Sell at price target"]] },
                { l: "9. Cash Position?", o: [["invested","Always fully invested"], ["tactical","Hold cash for dips"], ["buffer","Always keep 20% cash"]] },
                { l: "10. Philosophy?", o: [["business","I own businesses"], ["ticker","I trade tickers"]] }
            ];
            let html = "";
            qs.forEach((q, i) => {
                html += `<div class="quiz-question"><label>${q.l}</label><select id="q${i}">`;
                q.o.forEach(opt => html += `<option value="${opt[0]}">${opt[1]}</option>`);
                html += `</select></div>`;
            });
            document.getElementById('quizQuestions').innerHTML = html;
        },
        processQuiz: () => {
            const scores = { Growth:0, Income:0, Safety:0, Value:0, Momentum:0 };
            const getVal = (i) => document.getElementById(`q${i}`).value;
            if(getVal(0)==='growth') scores.Growth+=3; if(getVal(0)==='income') scores.Income+=3; if(getVal(0)==='safety') scores.Safety+=3;
            if(getVal(1)==='buy') { scores.Growth+=1; scores.Value+=1; } if(getVal(1)==='sell') scores.Safety+=2;
            if(getVal(4)==='quality') scores.Growth+=1; if(getVal(4)==='value') scores.Value+=2; if(getVal(4)==='trend') scores.Momentum+=2;
            if(getVal(6)==='love') scores.Value+=1; if(getVal(6)==='hate') scores.Safety+=2;
            if(getVal(9)==='business') scores.Growth+=1; else scores.Momentum+=1;

            let typeKey = "Compounder"; 
            if (getVal(2) === 'high') typeKey = "LiquidityConstrained";
            else if (scores.Safety >= 5) typeKey = "RiskMinimizer";
            else if (scores.Income >= 3) typeKey = "Income";
            else if (scores.Momentum >= 3) typeKey = "Redeployer";
            else if (getVal(5) === 'high') typeKey = "Concentrator";
            else if (scores.Value >= 4) typeKey = "ValuationAnchored";
            
            Store.profile = { type: typeKey, timestamp: Date.now() };
            Store.saveProfile();
            ProfileEngine.renderDashboard();
            UI.toast("Profile Generated");
        },
        renderDashboard: () => {
            document.getElementById('quizView').classList.add('hidden');
            document.getElementById('profileDashboard').classList.remove('hidden');
            document.getElementById('retakeQuizBtn').classList.remove('hidden');
            const type = InvestorTypes[Store.profile.type];
            document.getElementById('profileTypeName').innerText = type.name;
            document.getElementById('profileTypeDesc').innerText = type.desc;
            const wContainer = document.getElementById('profileWeights');
            wContainer.innerHTML = '';
            for (const [key, val] of Object.entries(type.weights)) {
                if(val > 0) wContainer.innerHTML += `<span class="weight-tag">${key.toUpperCase()}: ${(val*100).toFixed(0)}%</span>`;
            }
        },
        runHealthCheck: () => {
            const grid = document.getElementById('healthGrid');
            grid.innerHTML = '<div class="empty-state"><i class="fa-solid fa-spinner fa-spin"></i> Diagnosing...</div>';
            if(Store.portfolio.length === 0) return grid.innerHTML = '<div class="empty-state">Portfolio is empty.</div>';
            Store.portfolio.forEach(stock => API.enqueue({ function: 'OVERVIEW', symbol: stock.symbol }, d => ProfileEngine.scoreStock(stock, d)));
        },
        scoreStock: (stock, data) => {
            const { score, raw } = ScoringEngine.calculate(data);
            const grid = document.getElementById('healthGrid');
            if(grid.querySelector('.empty-state')) grid.innerHTML = '';
            let status = "Hold", statusClass = "status-hold";
            if (score < 40) { status = "Exit Prep"; statusClass = "status-exit"; }
            else if (score < 60) { status = "Reduce"; statusClass = "status-reduce"; }
            else if (score < 75) { status = "Watch"; statusClass = "status-watch"; }
            const card = document.createElement('div');
            card.className = 'health-card';
            card.innerHTML = `<div class="health-score-box"><span class="health-score-val" style="color:${score>70?'var(--success)':(score<50?'var(--danger)':'var(--warning)')}">${score}</span><small>Score</small></div><div class="health-details"><h4>${stock.symbol} <span class="health-status ${statusClass}">${status}</span></h4><p class="health-reason" style="margin-bottom:0.5rem">Diagnostics</p><div class="data-grid-mini"><div class="mini-item"><span class="mini-label">Growth</span><span class="mini-val">${raw.revG}%</span></div><div class="mini-item"><span class="mini-label">ROE</span><span class="mini-val">${raw.roe}%</span></div><div class="mini-item"><span class="mini-label">D/E</span><span class="mini-val">${parseFloat(raw.debt).toFixed(2)}</span></div><div class="mini-item"><span class="mini-label">Trend</span><span class="mini-val" style="color:${raw.price>raw.ma200?'var(--success)':'var(--danger)'}">${raw.price>raw.ma200?'Bull':'Bear'}</span></div></div></div>`;
            grid.appendChild(card);
        }
    };

    const App = {
        charts: { alloc: null, perf: null },
        results: { sell: [], buy: [], firewall: [] },

        init: () => {
            try {
                // FIXED ORDER: Charts first, then Data
                App.initCharts();
                UI.renderPortfolio();
                App.setupEventListeners();
                ProfileEngine.init();
                if(Store.getApiKey()) document.getElementById('apiStatusDot').style.background = 'var(--success)';
                console.log("App Initialized");
            } catch (e) {
                console.error(e);
                UI.toast("Init Failed", "error");
            }
        },
        setupEventListeners: () => {
            document.querySelectorAll('.nav-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
                    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
                    btn.classList.add('active');
                    document.getElementById(btn.getAttribute('data-tab')).classList.add('active');
                });
            });
            document.getElementById('refreshBtn').addEventListener('click', () => {
                if(Store.portfolio.length === 0) return UI.toast("No stocks to update", "error");
                UI.toast(`Queuing ${Store.portfolio.length} price updates...`);
                document.getElementById('lastUpdated').innerText = `Updating...`;
                Store.portfolio.forEach((s, idx) => App.updateSingleStock(idx, true));
            });
            const modal = document.getElementById('stockModal');
            document.getElementById('addStockBtn').addEventListener('click', () => { document.getElementById('stockForm').reset(); document.getElementById('editIndex').value = ''; modal.classList.add('open'); });
            document.querySelectorAll('.close-modal').forEach(b => b.addEventListener('click', () => modal.classList.remove('open')));
            document.getElementById('saveKeyBtn').addEventListener('click', () => { Store.setApiKey(document.getElementById('apiKeyInput').value); document.getElementById('apiStatusDot').style.background = 'var(--success)'; UI.toast('API Key Connected'); });
            document.getElementById('stockForm').addEventListener('submit', (e) => {
                e.preventDefault();
                const stock = { symbol: document.getElementById('mSymbol').value.toUpperCase(), shares: parseFloat(document.getElementById('mShares').value), price: parseFloat(document.getElementById('mPrice').value), conviction: document.getElementById('mConviction').value, thesis: document.getElementById('mThesis').value, currentPrice: parseFloat(document.getElementById('mPrice').value) };
                const idx = document.getElementById('editIndex').value;
                if (idx !== '') { stock.id = Store.portfolio[idx].id; stock.currentPrice = Store.portfolio[idx].currentPrice; Store.portfolio[idx] = stock; } else { stock.id = Store.generateId(); Store.portfolio.push(stock); }
                Store.savePortfolio(); UI.renderPortfolio(); modal.classList.remove('open'); UI.toast('Portfolio Updated');
            });
            document.getElementById('portfolioList').addEventListener('click', (e) => {
                const btn = e.target.closest('.action-btn');
                if(!btn) return;
                const idx = btn.getAttribute('data-index');
                if(btn.classList.contains('edit-btn')) App.editStock(idx);
                else if(btn.classList.contains('delete-btn')) App.deleteStock(btn.getAttribute('data-id'));
                else if(btn.classList.contains('refresh-btn')) App.updateSingleStock(idx);
            });

            const runScan = (mode) => {
                if ((mode === 'sell' || mode === 'buy') && !Store.profile) {
                    document.getElementById(mode + 'Grid').innerHTML = '';
                    document.getElementById(mode + 'ProfileAlert').classList.remove('hidden');
                    return;
                }
                if(document.getElementById(mode + 'ProfileAlert')) document.getElementById(mode + 'ProfileAlert').classList.add('hidden');
                
                const gridId = mode === 'sell' ? 'sellGrid' : (mode === 'buy' ? 'buyGrid' : 'firewallGrid');
                const grid = document.getElementById(gridId);
                grid.innerHTML = '<div class="empty-state"><i class="fa-solid fa-spinner fa-spin"></i> Scanning...</div>';
                if(Store.portfolio.length === 0) return grid.innerHTML = '<div class="empty-state">Portfolio is empty.</div>';
                
                App.results[mode] = [];
                let processedCount = 0;
                const totalValue = Store.portfolio.reduce((acc, s) => acc + ((s.currentPrice || s.price) * s.shares), 0);
                Store.portfolio.forEach(stock => {
                    API.enqueue({ function: 'OVERVIEW', symbol: stock.symbol }, d => {
                        const { score, raw } = ScoringEngine.calculate(d);
                        const val = (stock.currentPrice || stock.price) * stock.shares;
                        const pct = totalValue > 0 ? (val / totalValue) : 0;
                        App.results[mode].push({ stock, score, raw, pct });
                        processedCount++;
                        if(processedCount === Store.portfolio.length) App.renderScanResults(mode);
                    });
                });
            };
            document.getElementById('runSellScanBtn').addEventListener('click', () => runScan('sell'));
            document.getElementById('runBuyScanBtn').addEventListener('click', () => runScan('buy'));
            document.getElementById('runAuditBtn').addEventListener('click', () => runScan('firewall'));
            
            document.getElementById('exportBtn').addEventListener('click', () => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify({ portfolio: Store.portfolio })], {type: 'application/json'})); a.download = `portfolio_${Date.now()}.json`; a.click(); });
            const handleImp = (e, replace) => { const reader = new FileReader(); reader.onload = (ev) => { try { Store.portfolio = replace ? JSON.parse(ev.target.result).portfolio : [...Store.portfolio, ...JSON.parse(ev.target.result).portfolio]; Store.savePortfolio(); UI.renderPortfolio(); UI.toast("Import Successful"); } catch(err) { UI.toast("Import Failed", "error"); } }; if(e.target.files.length > 0) reader.readAsText(e.target.files[0]); };
            document.getElementById('importMerge').onchange = (e) => handleImp(e, false); document.getElementById('importReplace').onchange = (e) => handleImp(e, true);
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

        renderScanResults: (mode) => {
            const grid = document.getElementById(mode === 'sell' ? 'sellGrid' : (mode === 'buy' ? 'buyGrid' : 'firewallGrid'));
            grid.innerHTML = '';
            
            const limits = getRebalanceLimits(Store.profile?.type);
            const sorted = App.results[mode];

            if (mode === 'sell') sorted.sort((a, b) => a.score - b.score);
            else if (mode === 'buy') sorted.sort((a, b) => b.score - a.score);
            else sorted.sort((a, b) => a.score - b.score);

            sorted.forEach(item => {
                const { stock, score, raw, pct } = item;
                let action = "", colorClass = "", reason = "";
                const pctStr = (pct * 100).toFixed(1) + "%";
                const maxAlloc = (limits.max * 100).toFixed(0) + "%";
                const isOverweight = pct > limits.max;

                if (score >= 80) {
                    if (isOverweight) { action = "Hold (Max Alloc)"; colorClass = "bg-warning"; reason = `Score ${score}. Overweight (${pctStr} > ${maxAlloc}).`; }
                    else { action = "Buy Aggressively"; colorClass = "bg-success"; reason = `Score ${score}. Room to add (${pctStr}).`; }
                } else if (score >= 60) {
                    if (isOverweight) { action = "Trim Position"; colorClass = "bg-overweight"; reason = `Score ${score}. Overweight (${pctStr}). Trim.`; }
                    else { action = "Hold / Add Small"; colorClass = "bg-buy-small"; reason = `Score ${score}. Safe to hold.`; }
                } else if (score >= 40) {
                    if (isOverweight) { action = "Aggressive Trim"; colorClass = "bg-overweight"; reason = `Score ${score}. Weak & Overweight.`; }
                    else { action = "Watch Closely"; colorClass = "bg-watch"; reason = `Score ${score}. Fundamentals deteriorating.`; }
                } else {
                    action = "Sell / Exit"; colorClass = "bg-danger"; reason = `Score ${score}. Thesis broken.`;
                }

                if (mode === 'sell' && !action.includes('Sell') && !action.includes('Trim') && !action.includes('Watch')) return;
                if (mode === 'buy' && !action.includes('Buy') && !action.includes('Add')) return;

                const card = document.createElement('div');
                card.className = 'audit-card';
                card.innerHTML = `
                    <div class="action-banner ${colorClass.replace('bg-', 'bg-')} text-white" style="background-color: var(--${colorClass.replace('bg-','')})">${action}</div>
                    <div class="audit-header">
                        <div><strong>${stock.symbol}</strong><div style="font-size:0.8rem; opacity:0.8">Alloc: ${pctStr} / Limit: ${maxAlloc}</div></div>
                        <div class="score-badge ${colorClass.replace('bg-', 'bg-')}" style="background-color: var(--${colorClass.replace('bg-','')})">${score}</div>
                    </div>
                    <div class="audit-body">
                        <p class="health-reason" style="margin-bottom:0.8rem; font-size:0.85rem; border-left:2px solid var(--accent); padding-left:8px;">${reason}</p>
                        <div class="data-grid-mini">
                            <div class="mini-item"><span class="mini-label">Growth</span><span class="mini-val ${parseFloat(raw.revG)>0?'positive':'negative'}">${raw.revG}%</span></div>
                            <div class="mini-item"><span class="mini-label">ROE</span><span class="mini-val ${parseFloat(raw.roe)>15?'positive':''}">${raw.roe}%</span></div>
                            <div class="mini-item"><span class="mini-label">D/E</span><span class="mini-val ${parseFloat(raw.debt)<1?'positive':'negative'}">${parseFloat(raw.debt).toFixed(2)}</span></div>
                            <div class="mini-item"><span class="mini-label">Trend</span><span class="mini-val ${raw.price>raw.ma200?'positive':'negative'}">${raw.price>raw.ma200?'Bull':'Bear'}</span></div>
                        </div>
                    </div>
                `;
                grid.appendChild(card);
            });
            if(grid.innerHTML === '') grid.innerHTML = '<div class="empty-state">No matching stocks found.</div>';
        },

        editStock: (idx) => {
            const s = Store.portfolio[idx];
            document.getElementById('mSymbol').value = s.symbol;
            document.getElementById('mShares').value = s.shares;
            document.getElementById('mPrice').value = s.price;
            document.getElementById('mConviction').value = s.conviction;
            document.getElementById('mThesis').value = s.thesis;
            document.getElementById('editIndex').value = idx;
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