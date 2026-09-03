/**
 * AuraInsights Discovery Dashboard Frontend Application
 */

class DashboardApp {
  constructor() {
    this.charts = {};
    this.categories = [];
    this.activeCategory = "FOUNDATION";
    this.debounceTimer = null;
    this.selectedEvidenceIds = new Set();
    this.init();
  }


  async init() {
    this.setupTabs();
    this.setupDropZone();
    await this.refreshAllData();
  }

  setupTabs() {
    const tabs = document.querySelectorAll(".nav-btn");
    tabs.forEach(btn => {
      btn.addEventListener("click", () => {
        tabs.forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach(tab => tab.classList.remove("active"));

        btn.classList.add("active");
        const tabId = btn.getAttribute("data-tab");
        const target = document.getElementById(tabId);
        if (target) target.classList.add("active");

        // Trigger chart resize / re-render if needed
        if (tabId === "problemTab") this.loadProblemData();
        if (tabId === "categoryTab") this.loadCategoryData();
        if (tabId === "evidenceTab") this.loadEvidenceData();
        if (tabId === "opportunityTab") this.loadOpportunityData();
        if (tabId === "validationTab") this.loadValidationData();
      });
    });
  }

  async refreshAllData() {
    await Promise.all([
      this.loadOverviewData(),
      this.loadProblemData(),
      this.loadCategoryData(),
      this.loadEvidenceData(),
      this.loadOpportunityData(),
      this.loadValidationData(),
    ]);
  }

  // ==========================================
  // 1. Overview Tab
  // ==========================================
  async loadOverviewData() {
    try {
      const [overview, themes, triggers] = await Promise.all([
        fetch("/api/overview").then(r => r.json()),
        fetch("/api/analytics/themes").then(r => r.json()),
        fetch("/api/analytics/triggers").then(r => r.json()),
      ]);

      document.getElementById("kpiTotalRecords").innerText = overview.total_analyzed_records || 0;
      document.getElementById("kpiConfidence").innerText = `${(overview.average_confidence_score * 100).toFixed(1)}%`;
      document.getElementById("kpiTopBlocker").innerText = themes[0] ? themes[0].theme_id.replace("_", " ") : "N/A";

      // Render Doughnut
      this.renderThemesDoughnut(themes);
      // Render Triggers Bar
      this.renderTriggersBar(triggers);

      // Render Dynamic Insights
      this.renderOverviewInsights(themes, triggers);
    } catch (e) {
      console.error("Failed to load overview data", e);
    }
  }

  renderThemesDoughnut(themes) {
    const ctx = document.getElementById("themesDoughnutChart");
    if (!ctx) return;

    if (this.charts.themes) this.charts.themes.destroy();

    const labels = themes.map(t => t.name || t.theme_id);
    const data = themes.map(t => t.frequency_pct);
    const colors = ["#F43F5E", "#F59E0B", "#10B981", "#A855F7", "#06B6D4", "#64748B"];

    this.charts.themes = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [{
          data: data,
          backgroundColor: colors,
          borderColor: "#111827",
          borderWidth: 3,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "right", labels: { color: "#CBD5E1", font: { size: 11, family: "Inter" } } },
          tooltip: {
            callbacks: {
              label: (item) => ` ${item.label}: ${item.parsed}%`
            }
          }
        }
      }
    });
  }

  renderTriggersBar(triggers) {
    const ctx = document.getElementById("triggersBarChart");
    if (!ctx) return;

    if (this.charts.triggers) this.charts.triggers.destroy();

    const top5 = triggers.slice(0, 5);
    this.charts.triggers = new Chart(ctx, {
      type: "bar",
      data: {
        labels: top5.map(t => t.trigger.replace(/_/g, " ")),
        datasets: [{
          label: "Frequency %",
          data: top5.map(t => t.frequency_pct),
          backgroundColor: "#6366F1",
          borderRadius: 6,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: "#94A3B8", font: { size: 10 } }, grid: { display: false } },
          y: { ticks: { color: "#94A3B8", callback: v => v + "%" }, grid: { color: "rgba(255,255,255,0.05)" } }
        }
      }
    });
  }

  renderOverviewInsights(themes, triggers) {
    const container = document.getElementById("overviewInsightsList");
    if (!container) return;

    const topTheme = themes[0] || { theme_id: "PRICE_VALUE", frequency_pct: 34 };
    const secondTheme = themes[1] || { theme_id: "SHADE_CONFIDENCE", frequency_pct: 26 };
    const topTrigger = triggers[0] || { trigger: "LOWER_PRICE", frequency_pct: 34 };

    container.innerHTML = `
      <div class="insight-item">
        <h4>🚨 #1 Friction Theme: ${topTheme.name || topTheme.theme_id}</h4>
        <p>Affects <strong>${topTheme.frequency_pct}%</strong> of analyzed shoppers. Primary barrier driving hesitation and delayed purchase.</p>
      </div>
      <div class="insight-item" style="border-left-color: #F43F5E;">
        <h4>🎨 Pre-Checkout Voids: ${secondTheme.name || secondTheme.theme_id}</h4>
        <p>Affects <strong>${secondTheme.frequency_pct}%</strong> of users. Buyers require real-world swatches and undertone validation before checkout.</p>
      </div>
      <div class="insight-item" style="border-left-color: #10B981;">
        <h4>🔓 Top Purchase Unlock: ${topTrigger.trigger.replace(/_/g, ' ')}</h4>
        <p>Present in <strong>${topTrigger.frequency_pct}%</strong> of decision paths. Direct catalyst that unblocks wishlists.</p>
      </div>
    `;
  }

  // ==========================================
  // 2. Problem Explorer Tab
  // ==========================================
  async loadProblemData() {
    const select = document.getElementById("problemCategoryFilter");
    const category = select ? select.value : "";

    try {
      const [blockers, gaps, channels] = await Promise.all([
        fetch(`/api/analytics/blockers${category ? `?category=${category}` : ""}`).then(r => r.json()),
        fetch("/api/analytics/gaps").then(r => r.json()),
        fetch("/api/analytics/channels").then(r => r.json()),
      ]);

      this.renderBlockersBar(blockers);
      this.renderGapsBar(gaps);
      this.renderChannelsBar(channels);
    } catch (e) {
      console.error("Failed to load problem explorer data", e);
    }
  }

  renderBlockersBar(blockers) {
    const ctx = document.getElementById("blockersBarChart");
    if (!ctx) return;
    if (this.charts.blockers) this.charts.blockers.destroy();

    const top8 = blockers.slice(0, 8);
    this.charts.blockers = new Chart(ctx, {
      type: "bar",
      data: {
        labels: top8.map(b => b.blocker.replace(/_/g, " ")),
        datasets: [{
          data: top8.map(b => b.frequency_pct),
          backgroundColor: "#F43F5E",
          borderRadius: 6,
        }]
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: "#94A3B8", callback: v => v + "%" }, grid: { color: "rgba(255,255,255,0.05)" } },
          y: { ticks: { color: "#CBD5E1", font: { size: 11 } }, grid: { display: false } }
        }
      }
    });
  }

  renderGapsBar(gaps) {
    const ctx = document.getElementById("gapsBarChart");
    if (!ctx) return;
    if (this.charts.gaps) this.charts.gaps.destroy();

    const top6 = gaps.slice(0, 6);
    this.charts.gaps = new Chart(ctx, {
      type: "bar",
      data: {
        labels: top6.map(g => g.information_gap.replace(/_/g, " ")),
        datasets: [{
          data: top6.map(g => g.frequency_pct),
          backgroundColor: "#06B6D4",
          borderRadius: 6,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: "#94A3B8", font: { size: 10 } }, grid: { display: false } },
          y: { ticks: { color: "#94A3B8", callback: v => v + "%" }, grid: { color: "rgba(255,255,255,0.05)" } }
        }
      }
    });
  }

  renderChannelsBar(channels) {
    const ctx = document.getElementById("channelsBarChart");
    if (!ctx) return;
    if (this.charts.channels) this.charts.channels.destroy();

    const filtered = channels.filter(c => c.channel !== "NONE").slice(0, 6);
    this.charts.channels = new Chart(ctx, {
      type: "bar",
      data: {
        labels: filtered.map(c => c.channel.replace(/_/g, " ")),
        datasets: [{
          data: filtered.map(c => c.frequency_pct),
          backgroundColor: "#A855F7",
          borderRadius: 6,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: "#94A3B8", font: { size: 11 } }, grid: { display: false } },
          y: { ticks: { color: "#94A3B8", callback: v => v + "%" }, grid: { color: "rgba(255,255,255,0.05)" } }
        }
      }
    });
  }

  // ==========================================
  // ==========================================
  // 3. Category Explorer Tab
  // ==========================================
  async loadCategoryData() {
    try {
      const catMatrix = await fetch("/api/analytics/categories").then(r => r.json());
      this.catMatrix = catMatrix;
      this.categories = Object.keys(catMatrix);

      // Ensure active category exists, default to FOUNDATION
      if (!this.activeCategory || !catMatrix[this.activeCategory]) {
        this.activeCategory = catMatrix["FOUNDATION"] ? "FOUNDATION" : this.categories[0];
      }

      // Populate filter pills
      const container = document.getElementById("categoryPillContainer");
      if (container) {
        container.innerHTML = this.categories.map(cat => `
          <button class="cat-pill ${cat === this.activeCategory ? 'active' : ''}" onclick="app.selectCategory('${cat}')">
            ${cat.replace(/_/g, ' ')} (${catMatrix[cat].total})
          </button>
        `).join("");
      }

      // Populate dropdowns across tabs
      this.populateCategoryDropdowns(this.categories);

      // Render Cross-Product Comparison Bar Chart
      this.renderCrossCategoryThemesBar(catMatrix);

      // Render active category profile & chart
      this.renderCategoryProfile(this.activeCategory, catMatrix[this.activeCategory]);
      this.renderCategoryThemesBar(this.activeCategory, catMatrix[this.activeCategory]);
    } catch (e) {
      console.error("Failed to load category explorer data", e);
    }
  }

  selectCategory(category) {
    this.activeCategory = category;
    document.querySelectorAll(".cat-pill").forEach(p => {
      p.classList.toggle("active", p.innerText.toUpperCase().includes(category.replace(/_/g, ' ')));
    });

    if (this.catMatrix && this.catMatrix[category]) {
      this.renderCategoryProfile(category, this.catMatrix[category]);
      this.renderCategoryThemesBar(category, this.catMatrix[category]);
    } else {
      this.loadCategoryData();
    }
  }

  renderCrossCategoryThemesBar(catMatrix) {
    const ctx = document.getElementById("crossCategoryThemesBarChart");
    if (!ctx) return;
    if (this.charts.crossCategoryThemes) this.charts.crossCategoryThemes.destroy();

    // 5 core behavioral themes requested
    const themesConfig = [
      { key: "PRICE_VALUE", label: "PRICE VALUE", color: "#F59E0B" },
      { key: "SHADE_CONFIDENCE", label: "SHADE CONFIDENCE", color: "#F43F5E" },
      { key: "COMPARISON", label: "COMPARISON", color: "#06B6D4" },
      { key: "SUITABILITY", label: "SUITABILITY", color: "#10B981" },
      { key: "QUALITY_TRUST", label: "QUALITY TRUST", color: "#A855F7" },
    ];

    // Calculate total count for each theme summed across all product categories
    let grandTotalStatements = 0;
    const totals = themesConfig.map(th => {
      let count = 0;
      Object.values(catMatrix).forEach(catData => {
        if (catData.themes && catData.themes[th.key]) {
          count += catData.themes[th.key];
        }
      });
      return count;
    });

    Object.values(catMatrix).forEach(catData => {
      grandTotalStatements += (catData.total || 0);
    });

    const labels = themesConfig.map(th => th.label);
    const bgColors = themesConfig.map(th => th.color);

    this.charts.crossCategoryThemes = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [{
          label: "Total Number of Statements (All Products)",
          data: totals,
          backgroundColor: bgColors,
          borderRadius: 8,
          borderWidth: 1,
          borderColor: "rgba(255, 255, 255, 0.12)",
          barPercentage: 0.6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false,
          },
          tooltip: {
            backgroundColor: "rgba(15, 23, 42, 0.95)",
            titleColor: "#FFFFFF",
            bodyColor: "#CBD5E1",
            borderColor: "rgba(255, 255, 255, 0.15)",
            borderWidth: 1,
            padding: 12,
            callbacks: {
              label: (context) => {
                const count = context.parsed.y;
                const pct = grandTotalStatements > 0 ? ((count / grandTotalStatements) * 100).toFixed(1) : 0;
                return ` ${count} statements (${pct}% of all ${grandTotalStatements.toLocaleString()} analyzed products)`;
              }
            }
          }
        },
        scales: {
          x: {
            ticks: {
              color: "#E2E8F0",
              font: { size: 12, weight: "600", family: "'Inter', sans-serif" },
              padding: 6,
            },
            grid: { display: false }
          },
          y: {
            ticks: {
              color: "#94A3B8",
              font: { size: 11 },
              stepSize: 200,
              callback: v => v.toLocaleString()
            },
            grid: { color: "rgba(255, 255, 255, 0.06)" }
          }
        }
      }
    });
  }

  renderCategoryThemesBar(category, catData) {
    const ctx = document.getElementById("categoryThemesBarChart");
    if (!ctx) return;
    if (this.charts.categoryThemes) this.charts.categoryThemes.destroy();

    const themesMap = catData ? (catData.themes || {}) : {};
    const total = catData ? (catData.total || 0) : 0;

    const themeDefinitions = [
      { key: "PRICE_VALUE", label: "Price & Value", color: "#F59E0B" },
      { key: "SHADE_CONFIDENCE", label: "Shade Confidence", color: "#F43F5E" },
      { key: "COMPARISON", label: "Comparison", color: "#06B6D4" },
      { key: "SUITABILITY", label: "Suitability", color: "#10B981" },
      { key: "QUALITY_TRUST", label: "Quality & Trust", color: "#A855F7" },
    ];

    const labels = themeDefinitions.map(t => t.label);
    const dataValues = themeDefinitions.map(t => themesMap[t.key] || 0);
    const bgColors = themeDefinitions.map(t => t.color);

    this.charts.categoryThemes = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [{
          label: `${category} Statement Count`,
          data: dataValues,
          backgroundColor: bgColors,
          borderRadius: 6,
        }]
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) => {
                const count = context.parsed.x;
                const pct = total > 0 ? ((count / total) * 100).toFixed(1) : 0;
                return ` ${count} statements (${pct}% of ${category.replace(/_/g, ' ')})`;
              }
            }
          }
        },
        scales: {
          x: {
            ticks: { color: "#94A3B8", font: { size: 10 } },
            grid: { color: "rgba(255,255,255,0.05)" }
          },
          y: {
            ticks: { color: "#E2E8F0", font: { size: 11, weight: "500" } },
            grid: { display: false }
          }
        }
      }
    });
  }

  populateCategoryDropdowns(categories) {
    const probSelect = document.getElementById("problemCategoryFilter");
    const evidSelect = document.getElementById("evidenceCategorySelect");

    if (probSelect && probSelect.options.length <= 1) {
      categories.forEach(c => {
        probSelect.innerHTML += `<option value="${c}">${c}</option>`;
      });
    }
    if (evidSelect && evidSelect.options.length <= 1) {
      categories.forEach(c => {
        evidSelect.innerHTML += `<option value="${c}">${c}</option>`;
      });
    }
  }

  async renderCategoryProfile(category, catData) {
    const titleEl = document.getElementById("categoryActiveTitle");
    const subtitleEl = document.getElementById("categoryActiveSubtitle");
    const profileBox = document.getElementById("categoryProfileBox");
    const quotesList = document.getElementById("categoryQuotesList");

    const formattedCategory = category.replace(/_/g, " ");
    if (titleEl) titleEl.innerText = `${formattedCategory} Behavioral Profile`;
    if (subtitleEl) subtitleEl.innerText = `Behavioral distribution count for ${formattedCategory} products`;

    if (profileBox && catData) {
      const themesList = Object.entries(catData.themes || {})
        .map(([t, cnt]) => `<strong>${t.replace(/_/g, " ")}:</strong> ${cnt} statements (${((cnt / catData.total) * 100).toFixed(1)}%)`)
        .join("<br>");

      profileBox.innerHTML = `
        <div class="profile-stat">
          <span>Total Analyzed Statements</span>
          <strong>${catData.total} records</strong>
        </div>
        <div class="profile-stat" style="flex-direction: column; align-items: flex-start; gap: 0.4rem;">
          <span>Theme Distribution Breakdown:</span>
          <div style="font-size: 0.82rem; color: #CBD5E1; line-height: 1.5;">${themesList}</div>
        </div>
      `;
    }

    // Fetch verbatim statements for this category
    try {
      const res = await fetch(`/api/evidence?category=${category}&limit=8`).then(r => r.json());
      if (quotesList) {
        quotesList.innerHTML = res.records.map(rec => `
          <div class="quote-card">
            <p>"${rec.verbatim_evidence || rec.raw_text}"</p>
            <div class="quote-meta">
              <span>Record #${rec.record_id} • Theme: ${(rec.theme || 'OTHER').replace(/_/g, ' ')}</span>
              <span>Confidence: ${(rec.confidence_score * 100).toFixed(0)}%</span>
            </div>
          </div>
        `).join("");
      }
    } catch (e) {
      console.error(e);
    }
  }

  // ==========================================
  // 4. Evidence Explorer Tab
  // ==========================================
  debounceEvidenceSearch() {
    clearTimeout(this.debounceTimer);
    this.debounceTimer = setTimeout(() => this.loadEvidenceData(), 300);
  }

  async loadEvidenceData() {
    const searchInput = document.getElementById("evidenceSearchInput");
    const catSelect = document.getElementById("evidenceCategorySelect");
    const themeSelect = document.getElementById("evidenceThemeSelect");

    const search = searchInput ? searchInput.value.trim() : "";
    const category = catSelect ? catSelect.value : "ALL";
    const theme = themeSelect ? themeSelect.value : "ALL";

    const params = new URLSearchParams();
    if (search) params.append("search", search);
    if (category && category !== "ALL") params.append("category", category);
    if (theme && theme !== "ALL") params.append("theme", theme);
    params.append("limit", 100);

    try {
      const data = await fetch(`/api/evidence?${params.toString()}`).then(r => r.json());
      const tbody = document.getElementById("evidenceTableBody");
      const countEl = document.getElementById("evidenceCountText");
      const masterCheckbox = document.getElementById("selectAllEvidenceCheckbox");
      if (masterCheckbox) masterCheckbox.checked = false;

      if (countEl) countEl.innerText = `Showing ${data.records.length} of ${data.total} records`;

      if (tbody) {
        if (data.records.length === 0) {
          tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: #94A3B8; padding: 2rem;">No matching evidence records found.</td></tr>`;
          this.updateBulkDeleteButton();
          return;
        }

        tbody.innerHTML = data.records.map(r => `
          <tr>
            <td style="text-align: center;">
              <input type="checkbox" class="evidence-row-checkbox" value="${r.record_id}" ${this.selectedEvidenceIds.has(r.record_id) ? 'checked' : ''} onchange="app.toggleEvidenceSelection('${r.record_id}', this)">
            </td>
            <td><strong>#${r.record_id}</strong></td>
            <td><span class="pill-conf" style="background: rgba(99,102,241,0.15); color: #818CF8;">${r.product_category}</span></td>
            <td><span class="pill-theme theme-${r.theme}">${(r.theme || 'OTHER').replace(/_/g, ' ')}</span></td>
            <td><span style="font-size: 0.78rem; color: #94A3B8;">${(r.wishlist_intent || 'OTHER').replace(/_/g, ' ')}</span></td>
            <td>
              <div style="font-style: italic; color: #E2E8F0; font-size: 0.83rem;">"${r.verbatim_evidence || r.raw_text}"</div>
            </td>
            <td>
              <span style="font-size: 0.75rem; color: #F43F5E;">${(r.purchase_blocker || []).join(', ')}</span>
            </td>
            <td><span class="pill-conf">${(r.confidence_score * 100).toFixed(0)}%</span></td>
            <td style="text-align: center;">
              <button class="btn-delete-row" title="Delete review #${r.record_id}" onclick="app.deleteSingleEvidence('${r.record_id}')">🗑️</button>
            </td>
          </tr>
        `).join("");
      }
      this.updateBulkDeleteButton();
    } catch (e) {
      console.error("Failed to load evidence data", e);
    }
  }

  toggleEvidenceSelection(recordId, checkbox) {
    if (checkbox.checked) {
      this.selectedEvidenceIds.add(recordId);
    } else {
      this.selectedEvidenceIds.delete(recordId);
    }
    this.updateBulkDeleteButton();
  }

  toggleSelectAllEvidence(masterCheckbox) {
    const checkboxes = document.querySelectorAll(".evidence-row-checkbox");
    checkboxes.forEach(cb => {
      cb.checked = masterCheckbox.checked;
      if (masterCheckbox.checked) {
        this.selectedEvidenceIds.add(cb.value);
      } else {
        this.selectedEvidenceIds.delete(cb.value);
      }
    });
    this.updateBulkDeleteButton();
  }

  updateBulkDeleteButton() {
    const btn = document.getElementById("evidenceBulkDeleteBtn");
    const countSpan = document.getElementById("selectedEvidenceCount");
    const count = this.selectedEvidenceIds.size;
    if (btn && countSpan) {
      countSpan.innerText = count;
      btn.style.display = count > 0 ? "inline-flex" : "none";
    }
  }

  async deleteSingleEvidence(recordId) {
    if (!confirm(`Are you sure you want to permanently delete review #${recordId}?`)) {
      return;
    }
    try {
      const res = await fetch(`/api/records/${encodeURIComponent(recordId)}`, {
        method: "DELETE"
      });
      if (res.ok) {
        this.selectedEvidenceIds.delete(recordId);
        await this.refreshAllData();
      } else {
        const err = await res.json();
        alert(`Failed to delete record: ${err.detail || "Unknown error"}`);
      }
    } catch (e) {
      alert(`Error deleting record: ${e.message}`);
    }
  }

  async deleteSelectedEvidence() {
    const count = this.selectedEvidenceIds.size;
    if (count === 0) return;
    if (!confirm(`Are you sure you want to permanently delete ${count} selected review(s)?`)) {
      return;
    }
    try {
      const res = await fetch("/api/records", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ record_ids: Array.from(this.selectedEvidenceIds) })
      });
      if (res.ok) {
        this.selectedEvidenceIds.clear();
        await this.refreshAllData();
      } else {
        const err = await res.json();
        alert(`Failed to delete records: ${err.detail || "Unknown error"}`);
      }
    } catch (e) {
      alert(`Error deleting records: ${e.message}`);
    }
  }


  // ==========================================
  // 5. Opportunity Prioritization Matrix Tab
  // ==========================================
  updateWeightAndRecalculate() {
    document.getElementById("shadeSolvVal").innerText = document.getElementById("shadeSolvSlider").value;
    document.getElementById("priceRelVal").innerText = document.getElementById("priceRelSlider").value;
    document.getElementById("suitImpVal").innerText = document.getElementById("suitImpSlider").value;
    document.getElementById("qualSolvVal").innerText = document.getElementById("qualSolvSlider").value;

    this.loadOpportunityData();
  }

  resetOpportunityWeights() {
    document.getElementById("shadeSolvSlider").value = 4.5;
    document.getElementById("priceRelSlider").value = 4.2;
    document.getElementById("suitImpSlider").value = 4.3;
    document.getElementById("qualSolvSlider").value = 3.8;
    this.updateWeightAndRecalculate();
  }

  async loadOpportunityData() {
    const shadeSolv = document.getElementById("shadeSolvSlider") ? document.getElementById("shadeSolvSlider").value : 4.5;
    const priceRel = document.getElementById("priceRelSlider") ? document.getElementById("priceRelSlider").value : 4.2;
    const suitImp = document.getElementById("suitImpSlider") ? document.getElementById("suitImpSlider").value : 4.3;
    const qualSolv = document.getElementById("qualSolvSlider") ? document.getElementById("qualSolvSlider").value : 3.8;

    const params = new URLSearchParams({
      shade_solv: shadeSolv,
      price_rel: priceRel,
      suit_imp: suitImp,
      qual_solv: qualSolv,
    });

    try {
      const opps = await fetch(`/api/opportunities?${params.toString()}`).then(r => r.json());
      const container = document.getElementById("opportunityCardsContainer");

      if (opps.length > 0) {
        document.getElementById("kpiTopOpportunity").innerText = `${opps[0].opportunity_score} pts`;
      }

      if (container) {
        container.innerHTML = opps.map((opp, idx) => `
          <div class="opp-card">
            <div>
              <div class="opp-card-header">
                <span class="opp-rank">#${idx + 1} Priority</span>
                <span class="opp-score-badge">${opp.opportunity_score} pts</span>
              </div>
              <h4 class="opp-title">${opp.name || opp.opportunity_theme}</h4>
              <p class="opp-desc">${opp.description}</p>
              
              <div class="opp-metrics-row">
                <div class="opp-metric-box">
                  <span>Frequency</span>
                  <strong>${opp.frequency_pct}%</strong>
                </div>
                <div class="opp-metric-box">
                  <span>Impact</span>
                  <strong>${opp.segment_impact_1_5} / 5</strong>
                </div>
                <div class="opp-metric-box">
                  <span>Solvability</span>
                  <strong>${opp.solvability_1_5} / 5</strong>
                </div>
              </div>
            </div>

            <div class="opp-evidence-box">
              "${opp.evidence_quotes[0] || 'No quote attached.'}"
            </div>
          </div>
        `).join("");
      }
    } catch (e) {
      console.error("Failed to load opportunities", e);
    }
  }

  // ==========================================
  // 6. AI Research Assistant (Chat)
  // ==========================================
  askAssistant(query) {
    document.getElementById("assistantInput").value = query;
    this.submitAssistantQuery();
  }

  async submitAssistantQuery() {
    const input = document.getElementById("assistantInput");
    const query = input.value.trim();
    if (!query) return;

    const chatContainer = document.getElementById("chatMessages");
    const askBtn = document.getElementById("askBtn");

    // Add user message bubble
    chatContainer.innerHTML += `
      <div class="chat-bubble user-bubble">
        <div class="bubble-avatar">👤</div>
        <div class="bubble-content">${query}</div>
      </div>
    `;

    // Add typing indicator
    const typingId = `typing_${Date.now()}`;
    chatContainer.innerHTML += `
      <div class="chat-bubble assistant-bubble" id="${typingId}">
        <div class="bubble-avatar">🤖</div>
        <div class="bubble-content"><div class="spinner" style="width: 20px; height: 20px;"></div></div>
      </div>
    `;

    input.value = "";
    askBtn.disabled = true;
    chatContainer.scrollTop = chatContainer.scrollHeight;

    try {
      const res = await fetch("/api/query/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query, top_k: 5 }),
      }).then(r => r.json());

      const typingEl = document.getElementById(typingId);
      if (typingEl) typingEl.remove();

      const citationsHtml = (res.cited_records || []).map(c => `
        <span class="citation-chip">#${c.record_id} (${c.category}): "${c.quote.slice(0, 60)}..."</span>
      `).join("");

      // Render Markdown-ish response
      const formattedAnswer = res.answer
        .replace(/### (.*?)\n/g, '<h4 style="color: #6366F1; margin-top: 0.5rem; margin-bottom: 0.2rem;">$1</h4>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n\n/g, '<p style="margin-bottom: 0.5rem;"></p>')
        .replace(/\n- /g, '<br>• ');

      chatContainer.innerHTML += `
        <div class="chat-bubble assistant-bubble">
          <div class="bubble-avatar">🤖</div>
          <div class="bubble-content">
            ${formattedAnswer}
            ${citationsHtml ? `<div style="margin-top: 0.75rem;"><strong style="font-size: 0.75rem; color: #94A3B8;">Cited Ground Truth Evidence:</strong><div class="citation-chips-row">${citationsHtml}</div></div>` : ''}
          </div>
        </div>
      `;
    } catch (e) {
      console.error(e);
      const typingEl = document.getElementById(typingId);
      if (typingEl) typingEl.remove();
      chatContainer.innerHTML += `
        <div class="chat-bubble assistant-bubble">
          <div class="bubble-avatar">🤖</div>
          <div class="bubble-content" style="color: #F43F5E;">Error communicating with discovery query engine. Please check backend.</div>
        </div>
      `;
    } finally {
      askBtn.disabled = false;
      chatContainer.scrollTop = chatContainer.scrollHeight;
    }
  }

  // ==========================================
  // 7. Phase 6: Validation & Human Review Tab
  // ==========================================
  async loadValidationData() {
    await this.loadReviewQueue();
  }

  async loadReviewQueue() {
    try {
      const queue = await fetch("/api/validation/review-queue?threshold=0.70").then(r => r.json());
      const tbody = document.getElementById("reviewQueueTableBody");

      if (tbody) {
        if (queue.length === 0) {
          tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #10B981; padding: 2rem;">✨ Zero unapproved or low-confidence records in queue. All records meet quality standards!</td></tr>`;
          return;
        }

        tbody.innerHTML = queue.map(r => `
          <tr>
            <td><strong>#${r.record_id}</strong></td>
            <td><span class="pill-conf" style="background: rgba(99,102,241,0.15); color: #818CF8;">${r.product_category}</span></td>
            <td style="font-style: italic; color: #E2E8F0; font-size: 0.82rem;">"${r.raw_text}"</td>
            <td><span class="pill-theme theme-${r.theme}">${r.theme || 'OTHER'}</span></td>
            <td><span class="pill-conf" style="background: rgba(244,63,94,0.15); color: #FB7185;">${(r.confidence_score * 100).toFixed(0)}%</span></td>
            <td>
              <button class="btn btn-secondary" style="padding: 0.3rem 0.6rem; font-size: 0.75rem;" onclick="app.approveRecord('${r.record_id}')">Approve ✓</button>
            </td>
          </tr>
        `).join("");
      }
    } catch (e) {
      console.error("Failed to load review queue", e);
    }
  }

  async approveRecord(recordId) {
    try {
      await fetch("/api/validation/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ record_id: recordId }),
      });
      await this.loadReviewQueue();
    } catch (e) {
      console.error("Failed to approve record", e);
    }
  }

  async runBenchmarkEvaluation() {
    alert("Running 100-sample gold standard benchmark evaluation...");
    try {
      const res = await fetch("/api/validation/benchmark-report").then(r => r.json());
      document.getElementById("benchMacroF1").innerText = `${(res.macro_f1 * 100).toFixed(1)}%`;
      document.getElementById("benchKappa").innerText = res.cohens_kappa.toFixed(3);
      alert(`Benchmark Completed!\nAccuracy: ${(res.accuracy * 100).toFixed(1)}%\nMacro F1: ${(res.macro_f1 * 100).toFixed(1)}%\nCohen's Kappa: ${res.cohens_kappa}\nGate Status: ${res.meets_gate_threshold ? "PASSED (>85% F1)" : "NEEDS TUNING"}`);
    } catch (e) {
      console.error(e);
      alert("Error running benchmark evaluation: " + e.message);
    }
  }

  // ==========================================
  // 8. Ingestion & File Upload
  // ==========================================
  setupDropZone() {
    const dropZone = document.getElementById("dropZone");
    if (!dropZone) return;

    dropZone.addEventListener("dragover", e => {
      e.preventDefault();
      dropZone.style.borderColor = "#6366F1";
    });

    dropZone.addEventListener("dragleave", e => {
      e.preventDefault();
      dropZone.style.borderColor = "rgba(99, 102, 241, 0.4)";
    });

    dropZone.addEventListener("drop", e => {
      e.preventDefault();
      dropZone.style.borderColor = "rgba(99, 102, 241, 0.4)";
      if (e.dataTransfer.files.length > 0) {
        this.uploadFile(e.dataTransfer.files[0]);
      }
    });
  }

  handleFileSelected(event) {
    if (event.target.files.length > 0) {
      this.uploadFile(event.target.files[0]);
    }
  }

  async uploadFile(file) {
    const progressBox = document.getElementById("uploadProgressBox");
    const resultBox = document.getElementById("uploadResultBox");

    if (progressBox) progressBox.style.display = "flex";
    if (resultBox) resultBox.style.display = "none";

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/ingest/upload", {
        method: "POST",
        body: formData,
      }).then(r => r.json());

      if (progressBox) progressBox.style.display = "none";
      if (resultBox) {
        resultBox.style.display = "block";
        resultBox.innerHTML = `
          <h4>🎉 Ingestion & Classification Complete!</h4>
          <p><strong>File:</strong> ${res.filename}</p>
          <p><strong>Parsed Records:</strong> ${res.parsed_records} | <strong>Classified:</strong> ${res.classified_records}</p>
        `;
      }

      await this.refreshAllData();
    } catch (e) {
      if (progressBox) progressBox.style.display = "none";
      if (resultBox) {
        resultBox.style.display = "block";
        resultBox.style.borderColor = "#F43F5E";
        resultBox.style.color = "#F43F5E";
        resultBox.innerHTML = `<h4>❌ Ingestion Failed</h4><p>${e.message}</p>`;
      }
    }
  }
}

// Instantiate App
window.app = new DashboardApp();
