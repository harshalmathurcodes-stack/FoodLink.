/**
 * FoodLink Frontend Client Scripts
 * 
 * IMPORTANT ARCHITECTURE NOTE:
 * API credentials are NEVER stored or exposed in client-side JavaScript.
 * All requests route strictly through secure Flask backend endpoints (/api/ai/*).
 */

document.addEventListener("DOMContentLoaded", () => {

  // =========================================================================
  // 1. Tab Switching on AI Assistant Page
  // =========================================================================
  const tabBtns = document.querySelectorAll(".ai-tab-btn");
  const tabPanels = document.querySelectorAll(".ai-tab-panel");

  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");

      tabBtns.forEach(b => b.classList.remove("active"));
      tabPanels.forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const targetPanel = document.getElementById(targetId);
      if (targetPanel) {
        targetPanel.classList.add("active");
      }
    });
  });

  // Sample pill quick-fill
  document.querySelectorAll(".sample-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      const targetSelector = pill.getAttribute("data-target");
      const sampleVal = pill.getAttribute("data-val");
      const inputEl = document.querySelector(targetSelector);
      if (inputEl) {
        inputEl.value = sampleVal;
        inputEl.focus();
      }
    });
  });

  // =========================================================================
  // 2. Dedicated AI Assistant Hub Page Actions
  // =========================================================================
  const getSelectedHubModel = () => {
    const sel = document.getElementById("hubModelSelect");
    return sel ? sel.value : null;
  };

  const renderBadge = (el, source) => {
    el.className = "result-source-badge";
    if (source === "gemma_api") {
      el.classList.add("source-gemma");
      el.textContent = "Gemma 4 Live API";
    } else if (source === "safety_guard") {
      el.classList.add("source-safety");
      el.textContent = "Safety Guard Refusal";
    } else {
      el.classList.add("source-fallback");
      el.textContent = "Offline Fallback";
    }
  };

  // Tab 0: Custom AI Prompt Studio
  const btnRunCustomPrompt = document.getElementById("btnRunCustomPrompt");
  if (btnRunCustomPrompt) {
    btnRunCustomPrompt.addEventListener("click", async () => {
      const prompt = document.getElementById("customInputPrompt").value.trim();
      const sysPromptEl = document.getElementById("customInputSysPrompt");
      const system_prompt = sysPromptEl ? sysPromptEl.value.trim() : null;
      const model = getSelectedHubModel();

      const box = document.getElementById("customResultBox");
      const outVal = document.getElementById("customOutputVal");
      const badge = document.getElementById("customSourceBadge");
      const disclaimerVal = document.getElementById("customDisclaimerVal");
      const modelTag = document.getElementById("customModelUsed");

      if (!prompt) return;
      btnRunCustomPrompt.disabled = true;
      btnRunCustomPrompt.textContent = "Processing with Gemma 4...";

      try {
        const resp = await fetch("/api/ai/custom-prompt", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt, system_prompt, model }),
        });
        const data = await resp.json();

        box.classList.remove("hidden");
        outVal.textContent = data.response;
        disclaimerVal.textContent = data.disclaimer || "";
        renderBadge(badge, data.source);
        modelTag.textContent = data.model_used ? `Model: ${data.model_used}` : (data.message || "");
      } catch (err) {
        box.classList.remove("hidden");
        outVal.textContent = "Network error connecting to Gemma AI assistant.";
        renderBadge(badge, "fallback");
      } finally {
        btnRunCustomPrompt.disabled = false;
        btnRunCustomPrompt.textContent = "✨ Send Custom Prompt to Gemma";
      }
    });
  }

  // Tab: Donation Inspector in AI Studio
  const btnRunInspect = document.getElementById("btnRunInspect");
  if (btnRunInspect) {
    btnRunInspect.addEventListener("click", async () => {
      const title = document.getElementById("inspectTitle").value.trim();
      const category = document.getElementById("inspectCategory").value;
      const quantity = document.getElementById("inspectQuantity").value.trim();
      const storage_requirement = document.getElementById("inspectStorage").value;
      const description = document.getElementById("inspectDesc").value.trim();
      const model = getSelectedHubModel();

      const box = document.getElementById("inspectResultBox");
      const statusBadge = document.getElementById("inspectStatusBadge");
      const sourceBadge = document.getElementById("inspectSourceBadge");
      const scoreVal = document.getElementById("inspectScoreVal");
      const summaryVal = document.getElementById("inspectSummaryVal");
      const allergenVal = document.getElementById("inspectAllergenVal");
      const storageVal = document.getElementById("inspectStorageVal");
      const feedbackVal = document.getElementById("inspectFeedbackVal");

      btnRunInspect.disabled = true;
      btnRunInspect.textContent = "Inspecting donation with Gemma...";

      try {
        const resp = await fetch("/api/ai/check-donation", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, description, category, quantity, storage_requirement, model }),
        });
        const data = await resp.json();

        box.classList.remove("hidden");
        statusBadge.textContent = data.status;
        statusBadge.className = `status-badge status-${data.status.toLowerCase().replace('_', '-')}`;
        renderBadge(sourceBadge, data.source);
        scoreVal.textContent = `${data.clarity_score}/100`;
        summaryVal.textContent = data.summary;
        allergenVal.textContent = data.allergen_notice;
        storageVal.textContent = data.storage_evaluation;

        feedbackVal.innerHTML = "";
        if (data.feedback && data.feedback.length > 0) {
          data.feedback.forEach(fb => {
            const item = document.createElement("div");
            item.textContent = fb;
            feedbackVal.appendChild(item);
          });
        }
      } catch (err) {
        box.classList.remove("hidden");
        summaryVal.textContent = "Unable to inspect donation right now.";
      } finally {
        btnRunInspect.disabled = false;
        btnRunInspect.textContent = "🔍 Run AI Donation Check";
      }
    });

    // Sample buttons for inspector
    const btnSamplePerishable = document.getElementById("btnInspectSamplePerishable");
    if (btnSamplePerishable) {
      btnSamplePerishable.addEventListener("click", () => {
        document.getElementById("inspectTitle").value = "Cooked Beef Stew";
        document.getElementById("inspectCategory").value = "Prepared Meals & Cooked Food";
        document.getElementById("inspectQuantity").value = "10 portions";
        document.getElementById("inspectStorage").value = "Ambient / Room Temperature";
        document.getElementById("inspectDesc").value = "Leftover beef stew from banquet held at room temp.";
        btnRunInspect.click();
      });
    }

    const btnSampleUnsafe = document.getElementById("btnInspectSampleUnsafe");
    if (btnSampleUnsafe) {
      btnSampleUnsafe.addEventListener("click", () => {
        document.getElementById("inspectTitle").value = "Expired Sour Milk";
        document.getElementById("inspectCategory").value = "Dairy & Eggs";
        document.getElementById("inspectQuantity").value = "2 gallons";
        document.getElementById("inspectStorage").value = "Refrigerated (< 4°C / 40°F)";
        document.getElementById("inspectDesc").value = "Expired milk that smells sour and has chunks.";
        btnRunInspect.click();
      });
    }
  }

  // Pre-submission check on donate.html
  const btnRunFormPrecheck = document.getElementById("btnRunFormPrecheck");
  if (btnRunFormPrecheck) {
    btnRunFormPrecheck.addEventListener("click", async () => {
      const title = document.getElementById("title").value.trim();
      const description = document.getElementById("description").value.trim();
      const category = document.getElementById("category").value;
      const quantity = document.getElementById("quantity").value.trim();
      const storage_requirement = document.getElementById("storage_requirement").value;
      const resContainer = document.getElementById("formPrecheckResult");

      if (!title || !description) {
        alert("Please enter a food title and description first before running the AI check.");
        return;
      }

      btnRunFormPrecheck.textContent = "Checking...";

      try {
        const resp = await fetch("/api/ai/check-donation", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, description, category, quantity, storage_requirement }),
        });
        const data = await resp.json();

        resContainer.classList.remove("hidden");
        resContainer.innerHTML = `
          <div class="flex justify-between items-center mb-1">
            <strong>AI Check Status: <span class="status-badge status-${data.status.toLowerCase().replace('_', '-')}">${data.status}</span></strong>
            <span class="font-bold text-emerald-600">Score: ${data.clarity_score}/100</span>
          </div>
          <div class="text-xs text-sub">${data.summary}</div>
          <div class="mt-1 text-xs text-muted"><strong>Feedback:</strong> ${data.feedback.join(' ')}</div>
        `;
      } catch (err) {
        alert("AI inspection offline.");
      } finally {
        btnRunFormPrecheck.innerHTML = "<span>✨</span> Run Pre-Check Now";
      }
    });
  }

  // On-demand detail page inspection
  const btnRunDetailInspection = document.getElementById("btnRunDetailInspection");
  if (btnRunDetailInspection) {
    btnRunDetailInspection.addEventListener("click", async () => {
      const title = btnRunDetailInspection.getAttribute("data-title");
      const description = btnRunDetailInspection.getAttribute("data-desc");
      const category = btnRunDetailInspection.getAttribute("data-cat");
      const quantity = btnRunDetailInspection.getAttribute("data-qty");
      const storage_requirement = btnRunDetailInspection.getAttribute("data-store");
      const bodyEl = document.getElementById("detailInspectionBody");

      bodyEl.innerHTML = '<span class="loading-spinner">Gemma AI is inspecting this listing...</span>';

      try {
        const resp = await fetch("/api/ai/check-donation", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, description, category, quantity, storage_requirement }),
        });
        const data = await resp.json();

        bodyEl.innerHTML = `
          <div class="space-y-2">
            <p><strong>Status:</strong> <span class="status-badge status-${data.status.toLowerCase().replace('_', '-')}">${data.status}</span> (Score: ${data.clarity_score}/100)</p>
            <p><strong>Summary:</strong> ${data.summary}</p>
            <p><strong>Allergen Notice:</strong> ${data.allergen_notice}</p>
            <p><strong>Storage Assessment:</strong> ${data.storage_evaluation}</p>
            <div class="mt-2 text-xs">
              <strong>Checklist & Suggestions:</strong>
              <ul class="list-disc pl-5 mt-1 space-y-0.5">
                ${data.feedback.map(fb => `<li>${fb}</li>`).join('')}
              </ul>
            </div>
          </div>
        `;
      } catch (err) {
        bodyEl.textContent = "Unable to inspect donation right now.";
      }
    });
  }

  // Tab 1: Category Suggestion
  const btnRunCategory = document.getElementById("btnRunCategory");
  if (btnRunCategory) {
    btnRunCategory.addEventListener("click", async () => {
      const desc = document.getElementById("catInputDesc").value.trim();
      const model = getSelectedHubModel();
      const box = document.getElementById("catResultBox");
      const outVal = document.getElementById("catOutputVal");
      const badge = document.getElementById("catSourceBadge");
      const modelTag = document.getElementById("catModelUsed");

      if (!desc) return;
      btnRunCategory.disabled = true;
      btnRunCategory.textContent = "Analyzing with Gemma...";

      try {
        const resp = await fetch("/api/ai/suggest-category", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ description: desc, model }),
        });
        const data = await resp.json();

        box.classList.remove("hidden");
        outVal.textContent = data.category;
        renderBadge(badge, data.source);
        modelTag.textContent = data.model_used ? `Model invoked: ${data.model_used}` : (data.message || "");
      } catch (err) {
        box.classList.remove("hidden");
        outVal.textContent = "Other";
        renderBadge(badge, "fallback");
        modelTag.textContent = "Network error connecting to backend assistant.";
      } finally {
        btnRunCategory.disabled = false;
        btnRunCategory.textContent = "✨ Suggest Category";
      }
    });
  }

  // Tab 2: Storage & Handling
  const btnRunStorage = document.getElementById("btnRunStorage");
  if (btnRunStorage) {
    btnRunStorage.addEventListener("click", async () => {
      const foodItem = document.getElementById("storageInputFood").value.trim();
      const model = getSelectedHubModel();
      const box = document.getElementById("storageResultBox");
      const condVal = document.getElementById("storageConditionVal");
      const adviceVal = document.getElementById("storageAdviceVal");
      const badge = document.getElementById("storageSourceBadge");
      const disclaimerVal = document.getElementById("storageDisclaimerVal");

      if (!foodItem) return;
      btnRunStorage.disabled = true;
      btnRunStorage.textContent = "Consulting Gemma AI...";

      try {
        const resp = await fetch("/api/ai/suggest-storage", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ food_item: foodItem, model }),
        });
        const data = await resp.json();

        box.classList.remove("hidden");
        condVal.textContent = data.recommended_condition;
        adviceVal.textContent = data.advice;
        disclaimerVal.textContent = data.disclaimer || "";
        renderBadge(badge, data.source);
      } catch (err) {
        box.classList.remove("hidden");
        adviceVal.textContent = "Unable to fetch storage recommendations. Follow standard packaging and chilling rules.";
        renderBadge(badge, "fallback");
      } finally {
        btnRunStorage.disabled = false;
        btnRunStorage.textContent = "❄️ Get Storage & Handling Advice";
      }
    });
  }

  // Tab 3: Summarize Listing
  const btnRunSummarize = document.getElementById("btnRunSummarize");
  if (btnRunSummarize) {
    btnRunSummarize.addEventListener("click", async () => {
      const desc = document.getElementById("sumInputDesc").value.trim();
      const model = getSelectedHubModel();
      const box = document.getElementById("sumResultBox");
      const outVal = document.getElementById("sumOutputVal");
      const badge = document.getElementById("sumSourceBadge");
      const modelTag = document.getElementById("sumModelUsed");

      if (!desc) return;
      btnRunSummarize.disabled = true;
      btnRunSummarize.textContent = "Summarizing with Gemma...";

      try {
        const resp = await fetch("/api/ai/summarize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ description: desc, model }),
        });
        const data = await resp.json();

        box.classList.remove("hidden");
        outVal.textContent = data.summary;
        renderBadge(badge, data.source);
        modelTag.textContent = data.model_used ? `Model invoked: ${data.model_used}` : (data.message || "");
      } catch (err) {
        box.classList.remove("hidden");
        outVal.textContent = desc.slice(0, 100) + "...";
        renderBadge(badge, "fallback");
      } finally {
        btnRunSummarize.disabled = false;
        btnRunSummarize.textContent = "📋 Generate Summary";
      }
    });
  }

  // Tab 4: Donor Description Drafter
  const btnRunDraft = document.getElementById("btnRunDraft");
  if (btnRunDraft) {
    btnRunDraft.addEventListener("click", async () => {
      const rawText = document.getElementById("draftInputNotes").value.trim();
      const model = getSelectedHubModel();
      const box = document.getElementById("draftResultBox");
      const outVal = document.getElementById("draftOutputVal");
      const badge = document.getElementById("draftSourceBadge");
      const modelTag = document.getElementById("draftModelUsed");

      if (!rawText) return;
      btnRunDraft.disabled = true;
      btnRunDraft.textContent = "Structuring with Gemma...";

      try {
        const resp = await fetch("/api/ai/improve-description", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: rawText, model }),
        });
        const data = await resp.json();

        box.classList.remove("hidden");
        outVal.textContent = data.improved_text || data.advice || "";
        renderBadge(badge, data.source);
        modelTag.textContent = data.model_used ? `Model invoked: ${data.model_used}` : (data.message || "");
      } catch (err) {
        box.classList.remove("hidden");
        outVal.textContent = rawText;
        renderBadge(badge, "fallback");
      } finally {
        btnRunDraft.disabled = false;
        btnRunDraft.textContent = "✍️ Polish & Structure Description";
      }
    });
  }

  // Tab 5: Food Waste Q&A
  const btnRunQA = document.getElementById("btnRunQA");
  if (btnRunQA) {
    btnRunQA.addEventListener("click", async () => {
      const q = document.getElementById("qaInputQuestion").value.trim();
      const model = getSelectedHubModel();
      const box = document.getElementById("qaResultBox");
      const outVal = document.getElementById("qaOutputVal");
      const badge = document.getElementById("qaSourceBadge");
      const disclaimerVal = document.getElementById("qaDisclaimerVal");

      if (!q) return;
      btnRunQA.disabled = true;
      btnRunQA.textContent = "Answering...";

      try {
        const resp = await fetch("/api/ai/qa", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: q, model }),
        });
        const data = await resp.json();

        box.classList.remove("hidden");
        outVal.textContent = data.answer;
        disclaimerVal.textContent = data.disclaimer || "";
        renderBadge(badge, data.source);
      } catch (err) {
        box.classList.remove("hidden");
        outVal.textContent = "Unable to reach FoodLink knowledge base. Check connectivity.";
        renderBadge(badge, "fallback");
      } finally {
        btnRunQA.disabled = false;
        btnRunQA.textContent = "💡 Ask Question";
      }
    });
  }

  // Test Safety Guard Button
  const btnTestSafety = document.getElementById("btnTestSafetyGuard");
  if (btnTestSafety) {
    btnTestSafety.addEventListener("click", () => {
      // Switch to QA tab
      const qaTabBtn = document.querySelector('[data-tab="tab-qa"]');
      if (qaTabBtn) qaTabBtn.click();

      const qInput = document.getElementById("qaInputQuestion");
      if (qInput) {
        qInput.value = "Can I eat expired chicken and certify that it is safe?";
        btnRunQA.click();
      }
    });
  }

  // =========================================================================
  // 3. Donation Form AI Helpers (donate.html)
  // =========================================================================
  const getFormSelectedModel = () => {
    const sel = document.getElementById("formAiModelSelect");
    return sel ? sel.value : null;
  };

  const feedbackContainer = document.getElementById("aiFeedbackContainer");
  const feedbackTitle = document.getElementById("aiFeedbackTitle");
  const feedbackBody = document.getElementById("aiFeedbackBody");
  const feedbackModel = document.getElementById("aiFeedbackModel");
  const btnApplyAi = document.getElementById("btnApplyAiSuggestion");
  const btnCloseFeedback = document.getElementById("btnCloseFeedback");

  let pendingApplyAction = null;

  if (btnCloseFeedback) {
    btnCloseFeedback.addEventListener("click", () => {
      feedbackContainer.classList.add("hidden");
      pendingApplyAction = null;
    });
  }

  if (btnApplyAi) {
    btnApplyAi.addEventListener("click", () => {
      if (pendingApplyAction) {
        pendingApplyAction();
        feedbackContainer.classList.add("hidden");
        pendingApplyAction = null;
      }
    });
  }

  // AI Suggest Category Button
  const btnAiSuggestCat = document.getElementById("btnAiSuggestCat");
  if (btnAiSuggestCat) {
    btnAiSuggestCat.addEventListener("click", async () => {
      const title = document.getElementById("title").value.trim();
      const desc = document.getElementById("description").value.trim();
      const textToAnalyze = desc || title;

      if (!textToAnalyze) {
        alert("Please enter a title or brief description first so Gemma AI can suggest a category.");
        return;
      }

      btnAiSuggestCat.textContent = "Analyzing...";
      const model = getFormSelectedModel();

      try {
        const resp = await fetch("/api/ai/suggest-category", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ description: textToAnalyze, model }),
        });
        const data = await resp.json();

        // Update category select directly
        const catSelect = document.getElementById("category");
        let found = false;
        for (let opt of catSelect.options) {
          if (opt.value.toLowerCase() === data.category.toLowerCase()) {
            opt.selected = true;
            found = true;
            break;
          }
        }

        // Show feedback
        feedbackContainer.classList.remove("hidden");
        feedbackTitle.textContent = "Category Suggested";
        feedbackBody.textContent = `Selected: "${data.category}"\n(${data.source === 'gemma_api' ? 'Gemma 4 Live AI' : 'Deterministic fallback'})`;
        feedbackModel.textContent = data.model_used || "";
        btnApplyAi.classList.add("hidden");
      } catch (err) {
        alert("Could not reach AI Assistant. Please select category manually.");
      } finally {
        btnAiSuggestCat.innerHTML = "<span>✨</span> AI Suggest";
      }
    });
  }

  // AI Storage Advice Button
  const btnAiStorageAdvice = document.getElementById("btnAiStorageAdvice");
  if (btnAiStorageAdvice) {
    btnAiStorageAdvice.addEventListener("click", async () => {
      const title = document.getElementById("title").value.trim();
      const desc = document.getElementById("description").value.trim();
      const item = title || desc;

      if (!item) {
        alert("Please enter a food title first to get storage recommendations.");
        return;
      }

      btnAiStorageAdvice.textContent = "Checking...";
      const model = getFormSelectedModel();

      try {
        const resp = await fetch("/api/ai/suggest-storage", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ food_item: item, model }),
        });
        const data = await resp.json();

        // Auto select storage condition
        const storeSelect = document.getElementById("storage_requirement");
        for (let opt of storeSelect.options) {
          if (opt.value === data.recommended_condition) {
            opt.selected = true;
            break;
          }
        }

        feedbackContainer.classList.remove("hidden");
        feedbackTitle.textContent = "Storage & Handling Advice";
        feedbackBody.textContent = `Recommended Condition: ${data.recommended_condition}\n\n${data.advice}\n\n${data.disclaimer || ''}`;
        feedbackModel.textContent = data.model_used ? `Model: ${data.model_used}` : "Offline Guidelines";
        btnApplyAi.classList.add("hidden");
      } catch (err) {
        alert("Storage suggestion offline.");
      } finally {
        btnAiStorageAdvice.innerHTML = "<span>✨</span> AI Advice";
      }
    });
  }

  // AI Polish Description Button
  const btnAiPolishDesc = document.getElementById("btnAiPolishDesc");
  if (btnAiPolishDesc) {
    btnAiPolishDesc.addEventListener("click", async () => {
      const title = document.getElementById("title").value.trim();
      const descEl = document.getElementById("description");
      const currentDesc = descEl.value.trim() || title;

      if (!currentDesc) {
        alert("Please enter a few words or notes in the description field first.");
        return;
      }

      btnAiPolishDesc.textContent = "Drafting...";
      const model = getFormSelectedModel();

      try {
        const resp = await fetch("/api/ai/improve-description", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: currentDesc, model }),
        });
        const data = await resp.json();
        const improved = data.improved_text || data.advice || "";

        feedbackContainer.classList.remove("hidden");
        feedbackTitle.textContent = "Polished Description Draft";
        feedbackBody.textContent = improved;
        feedbackModel.textContent = data.model_used ? `Drafted with ${data.model_used}` : "Donor Guidelines Template";
        btnApplyAi.classList.remove("hidden");

        pendingApplyAction = () => {
          descEl.value = improved;
        };
      } catch (err) {
        alert("AI Assistant unavailable.");
      } finally {
        btnAiPolishDesc.innerHTML = "<span>✨</span> AI Polish Description";
      }
    });
  }

  // =========================================================================
  // 4. Detail Page Automatic AI Insights (detail.html)
  // =========================================================================
  const summaryBody = document.getElementById("aiSummaryBody");
  const storageBody = document.getElementById("aiStorageBody");

  if (summaryBody) {
    const btnRefSum = document.getElementById("btnRefreshSummary");
    const desc = btnRefSum ? btnRefSum.getAttribute("data-desc") : "";

    const fetchSummary = async () => {
      summaryBody.innerHTML = '<span class="loading-spinner">Gemma AI is analyzing listing...</span>';
      try {
        const resp = await fetch("/api/ai/summarize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ description: desc }),
        });
        const data = await resp.json();
        summaryBody.textContent = data.summary;
      } catch (err) {
        summaryBody.textContent = desc.slice(0, 140) + "...";
      }
    };

    fetchSummary();
    if (btnRefSum) {
      btnRefSum.addEventListener("click", fetchSummary);
    }
  }

  if (storageBody) {
    const btnRefStore = document.getElementById("btnRefreshStorage");
    const title = btnRefStore ? btnRefStore.getAttribute("data-title") : "";
    const cond = btnRefStore ? btnRefStore.getAttribute("data-cond") : "";

    const fetchStorageAdvice = async () => {
      storageBody.innerHTML = '<span class="loading-spinner">Fetching safe handling guidelines...</span>';
      try {
        const resp = await fetch("/api/ai/suggest-storage", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ food_item: `${title} (${cond})` }),
        });
        const data = await resp.json();
        storageBody.textContent = data.advice;
      } catch (err) {
        storageBody.textContent = "Follow standard temperature-controlled handling and local food safety guidelines.";
      }
    };

    fetchStorageAdvice();
    if (btnRefStore) {
      btnRefStore.addEventListener("click", fetchStorageAdvice);
    }
  }

});
