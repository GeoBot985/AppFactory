document.addEventListener('DOMContentLoaded', () => {
    const modelSelect = document.getElementById('model-select');
    const statusArea = document.getElementById('status-area');
    const chatArea = document.getElementById('chat-area');
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const debugOutput = document.getElementById('debug-output');
    const evidenceOutput = document.getElementById('evidence-output');

    // Ingestion UI elements
    const pdfFileInput = document.getElementById('pdf-file-input');
    const browsePdfBtn = document.getElementById('browse-pdf-btn');
    const selectedPdfPath = document.getElementById('selected-pdf-path');
    const selectedFilesContainer = document.getElementById('selected-files-container');
    const ingestPdfBtn = document.getElementById('ingest-pdf-btn');
    const ingestStatusArea = document.getElementById('ingest-status-area');
    const batchResultsArea = document.getElementById('batch-results-area');

    // Corpus Panel elements
    const corpusList = document.getElementById('corpus-list');
    const refreshCorpusBtn = document.getElementById('refresh-corpus-btn');
    const selectAllBtn = document.getElementById('select-all-btn');
    const clearSelectionBtn = document.getElementById('clear-selection-btn');
    const removeSelectedBtn = document.getElementById('remove-selected-btn');
    const retrievalScopeText = document.getElementById('retrieval-scope-text');

    // Stats elements
    const statDocs = document.getElementById('stat-docs');
    const statChunks = document.getElementById('stat-chunks');
    const statSelected = document.getElementById('stat-selected');
    const statLastIngest = document.getElementById('stat-last-ingest');

    // Management elements
    const clearConfirmCheck = document.getElementById('clear-confirm-check');
    const clearCorpusBtn = document.getElementById('clear-corpus-btn');

    let allDocuments = [];
    let selectedDocumentIds = new Set();

    // Fetch models on load
    async function loadModels() {
        try {
            const response = await fetch('/api/models');
            const data = await response.json();

            modelSelect.innerHTML = '';

            if (data.error) {
                statusArea.textContent = data.error;
                const option = document.createElement('option');
                option.value = "";
                option.textContent = "No models available";
                modelSelect.appendChild(option);
                sendBtn.disabled = true;
            } else if (data.models && data.models.length > 0) {
                statusArea.textContent = "";
                data.models.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model;
                    option.textContent = model;
                    modelSelect.appendChild(option);
                });
                sendBtn.disabled = false;
            } else {
                statusArea.textContent = "No local models found. Pull a model via ollama.";
                const option = document.createElement('option');
                option.value = "";
                option.textContent = "Empty";
                modelSelect.appendChild(option);
                sendBtn.disabled = true;
            }
        } catch (error) {
            statusArea.textContent = "Failed to communicate with backend.";
            sendBtn.disabled = true;
        }
    }

    function appendMessage(role, text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        msgDiv.textContent = text;
        chatArea.appendChild(msgDiv);
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    function renderEvidence(chunks) {
        evidenceOutput.innerHTML = '';
        if (!chunks || chunks.length === 0) {
            evidenceOutput.innerHTML = '<div class="empty-evidence-msg">No evidence used.</div>';
            return;
        }

        chunks.forEach((chunk, idx) => {
            const chunkDiv = document.createElement('div');
            chunkDiv.className = 'evidence-chunk';

            const header = document.createElement('div');
            header.className = 'evidence-chunk-header';

            const titleSpan = document.createElement('span');
            titleSpan.textContent = `[Doc: ${chunk.document_name} | Chunk ${chunk.chunk_index}]`;

            const expandBtn = document.createElement('button');
            expandBtn.className = 'expand-btn';
            expandBtn.textContent = 'Expand';

            header.appendChild(titleSpan);
            header.appendChild(expandBtn);

            const textDiv = document.createElement('div');
            textDiv.className = 'evidence-chunk-text collapsed';
            textDiv.textContent = chunk.text;

            expandBtn.addEventListener('click', () => {
                if (textDiv.classList.contains('collapsed')) {
                    textDiv.classList.remove('collapsed');
                    expandBtn.textContent = 'Collapse';
                } else {
                    textDiv.classList.add('collapsed');
                    expandBtn.textContent = 'Expand';
                }
            });

            chunkDiv.appendChild(header);
            chunkDiv.appendChild(textDiv);
            evidenceOutput.appendChild(chunkDiv);
        });
    }

    function formatChatDebug(payload) {
        if (!payload) return "No debug payload.";

        let output = "[CHAT REQUEST]\n";
        output += `User message:\n${payload.user_message || 'N/A'}\n\n`;
        output += `Model:\n${payload.selected_model || 'N/A'}\n\n`;

        output += `[RAG]\n`;
        output += `RAG enabled:\n${payload.rag_enabled ? 'true' : 'false'}\n`;
        output += `Scope: ${payload.retrieval_scope || 'full_corpus'}\n`;
        output += `Selected docs count: ${payload.selected_documents_count || 0}\n`;
        if (payload.selected_documents_names && payload.selected_documents_names.length > 0) {
            output += `Selected docs: ${payload.selected_documents_names.join(', ')}\n`;
        }
        output += `\n`;

        if (payload.rag_enabled) {
            output += `Retrieval query:\n${payload.retrieval_query || 'N/A'}\n\n`;

            if (payload.retrieval_metrics) {
                const m = payload.retrieval_metrics;
                output += `[RETRIEVAL METRICS]\n`;
                output += `Eligible docs: ${m.eligible_docs}\n`;
                output += `Total candidate chunks: ${m.candidate_count}\n`;
                output += `Pool size for reranking: ${m.pool_size}\n\n`;
            }

            const chunks = payload.retrieval_chunks || [];
            output += `Retrieved chunks count:\n${chunks.length}\n\n`;
            output += `Retrieved chunks (ranked):\n`;

            if (chunks.length === 0) {
                output += `0 results\n`;
            } else {
                chunks.forEach((chunk, index) => {
                    const text = chunk.text || "";
                    const truncatedChunk = text.length > 500 ? text.substring(0, 500) + '...' : text;
                    output += `\n[${index + 1}] score=${chunk.score.toFixed(4)} | v=${chunk.vector_score.toFixed(4)} | l=${chunk.lexical_score.toFixed(4)}\n`;
                    output += `Doc: ${chunk.document_name} (index: ${chunk.chunk_index})\n`;
                    output += `Text length: ${text.length}\n`;
                    output += `${truncatedChunk}\n`;
                });
            }
            output += `\n`;
        }

        output += `[WATCHER]\n`;
        if (payload.watcher_enabled === false) {
            output += `enabled: false\nstatus: skipped\n\n`;
        } else {
            output += `enabled: true\n`;
            output += `allowed: ${payload.watcher_allowed !== undefined ? payload.watcher_allowed : 'N/A'}\n`;
            output += `modified: ${payload.watcher_modified !== undefined ? payload.watcher_modified : 'N/A'}\n`;

            const notes = payload.watcher_notes || [];
            if (notes.length > 0) {
                output += `notes:\n`;
                notes.forEach(note => {
                    output += `- ${note}\n`;
                });
            } else {
                output += `notes: none\n`;
            }
            output += `error: ${payload.watcher_error || 'none'}\n\n`;

            const ruleResults = payload.watcher_rule_results || [];
            if (ruleResults.length > 0) {
                output += `[WATCHER RULES]\n`;

                const summary = { error: 0, warning: 0, info: 0 };
                ruleResults.forEach(r => {
                    if (!r.passed) {
                        summary[r.severity]++;
                    }
                });

                output += `Summary:\n`;
                output += `  errors: ${summary.error}\n`;
                output += `  warnings: ${summary.warning}\n`;
                output += `  info: ${summary.info}\n\n`;

                ruleResults.forEach(r => {
                    const statusText = r.passed ? "passed" : "!! FAILED !!";
                    output += `${r.rule_id}: ${statusText}\n`;
                    output += `  severity: ${r.severity}\n`;
                    output += `  passed: ${r.passed}\n`;
                    if (!r.passed && r.details) {
                        output += `  details: ${r.details}\n`;
                    }
                    output += `\n`;
                });
            }
        }

        let promptToDisplay = payload.final_prompt || 'N/A';
        if (promptToDisplay.length > 8000) {
            promptToDisplay = promptToDisplay.substring(0, 8000) + '\n\n[...prompt truncated for display...]';
        }

        output += `[FINAL PROMPT]\nFinal prompt sent to model:\n${promptToDisplay}\n\n`;

        output += `[MODEL RESPONSE PREVIEW]\nModel response preview:\n${payload.response_preview || 'N/A'}\n\n`;

        output += `[ERRORS]\nErrors:\n`;
        output += `retrieval: ${payload.retrieval_error || 'none'}\n`;
        output += `ollama: ${payload.ollama_error || 'none'}\n`;

        return output;
    }

    async function sendMessage() {
        const message = messageInput.value.trim();
        const model = modelSelect.value;

        if (!message) return;
        if (!model) {
            statusArea.textContent = "Please select a model.";
            return;
        }

        statusArea.textContent = "";

        // Append user message
        appendMessage('user', message);
        messageInput.value = '';

        // Disable input while processing
        sendBtn.disabled = true;
        messageInput.disabled = true;

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    model,
                    message,
                    document_ids: selectedDocumentIds.size > 0 ? Array.from(selectedDocumentIds) : null
                })
            });

            const data = await response.json();

            // Render assistant reply or error
            if (data.debug && data.debug.error) {
                appendMessage('assistant', `System Error: ${data.debug.error}`);
            } else if (data.reply) {
                appendMessage('assistant', data.reply);
            } else {
                appendMessage('assistant', 'Empty response.');
            }

            // Render evidence
            renderEvidence(data.evidence);

            // Render debug trace
            debugOutput.textContent = formatChatDebug(data.debug);

        } catch (error) {
            statusArea.textContent = `Error sending request: ${error.message}`;
        } finally {
            sendBtn.disabled = false;
            messageInput.disabled = false;
            messageInput.focus();
        }
    }

    sendBtn.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // --- Ingestion Logic ---

    browsePdfBtn.addEventListener('click', () => {
        pdfFileInput.click();
    });

    pdfFileInput.addEventListener('change', () => {
        if (pdfFileInput.files && pdfFileInput.files.length > 0) {
            const files = Array.from(pdfFileInput.files);
            const count = files.length;

            selectedFilesContainer.innerHTML = '';
            const title = document.createElement('div');
            title.textContent = `Selected files (${count}):`;
            title.style.fontWeight = 'bold';
            selectedFilesContainer.appendChild(title);

            const list = document.createElement('ul');
            list.style.margin = '5px 0';
            list.style.paddingLeft = '20px';
            list.style.fontSize = '0.9em';

            // Limit display to first 5
            const displayLimit = 5;
            files.slice(0, displayLimit).forEach(f => {
                const li = document.createElement('li');
                li.textContent = f.name;
                list.appendChild(li);
            });

            if (count > displayLimit) {
                const li = document.createElement('li');
                li.textContent = `... and ${count - displayLimit} more`;
                list.appendChild(li);
            }

            selectedFilesContainer.appendChild(list);
            ingestPdfBtn.disabled = false;
        } else {
            selectedFilesContainer.innerHTML = '<span id="selected-pdf-path">No files selected.</span>';
            ingestPdfBtn.disabled = true;
        }
    });

    function updateScopeStatus() {
        if (selectedDocumentIds.size === 0) {
            retrievalScopeText.textContent = "Full corpus";
            removeSelectedBtn.disabled = true;
        } else {
            retrievalScopeText.textContent = `Working set (${selectedDocumentIds.size} documents)`;
            removeSelectedBtn.disabled = false;
        }
        statSelected.textContent = selectedDocumentIds.size;
    }

    function toggleDocumentSelection(docId) {
        if (selectedDocumentIds.has(docId)) {
            selectedDocumentIds.delete(docId);
        } else {
            selectedDocumentIds.add(docId);
        }
        renderDocumentCards();
        updateScopeStatus();
    }

    function renderDocumentCards() {
        corpusList.innerHTML = '';
        if (allDocuments.length === 0) {
            const emptyMsg = document.createElement('div');
            emptyMsg.className = 'empty-corpus-msg';
            emptyMsg.textContent = 'No indexed documents.';
            corpusList.appendChild(emptyMsg);
            return;
        }

        allDocuments.forEach(doc => {
            const card = document.createElement('div');
            card.className = `doc-card ${selectedDocumentIds.has(doc.document_id) ? 'selected' : ''}`;

            const name = document.createElement('div');
            name.className = 'doc-name';
            name.textContent = doc.document_name;

            const typeBadge = document.createElement('span');
            typeBadge.textContent = (doc.file_type || 'pdf').toUpperCase();
            typeBadge.style.fontSize = '0.7rem';
            typeBadge.style.backgroundColor = '#e3f2fd';
            typeBadge.style.padding = '2px 4px';
            typeBadge.style.borderRadius = '3px';
            typeBadge.style.marginLeft = '8px';
            typeBadge.style.color = '#1976d2';
            typeBadge.style.verticalAlign = 'middle';
            name.appendChild(typeBadge);

            if (doc.ocr_used) {
                const ocrBadge = document.createElement('span');
                ocrBadge.textContent = 'OCR';
                ocrBadge.style.fontSize = '0.7rem';
                ocrBadge.style.backgroundColor = '#eee';
                ocrBadge.style.padding = '2px 4px';
                ocrBadge.style.borderRadius = '3px';
                ocrBadge.style.marginLeft = '8px';
                ocrBadge.style.color = '#666';
                ocrBadge.style.verticalAlign = 'middle';
                name.appendChild(ocrBadge);
            }

            const meta = document.createElement('div');
            meta.className = 'doc-meta';
            const date = new Date(doc.ingested_at).toLocaleString();
            const sizeKB = (doc.file_size_bytes / 1024).toFixed(1);
            let ocrMeta = doc.ocr_used ? ` | OCR: ${doc.ocr_char_count} chars, ${doc.ocr_page_count} pages` : '';
            meta.innerHTML = `
                <span style="font-family: monospace; font-size: 0.7rem; color: #999;">ID: ${doc.document_id}</span><br>
                Path: ${doc.source_path || 'N/A'}<br>
                Ingested: ${date}<br>
                Chunks: ${doc.chunk_count} | Size: ${sizeKB} KB${ocrMeta}
            `;

            card.appendChild(name);
            card.appendChild(meta);

            card.addEventListener('click', () => toggleDocumentSelection(doc.document_id));
            corpusList.appendChild(card);
        });
    }

    async function loadStats() {
        try {
            const response = await fetch('/api/stats');
            const data = await response.json();
            if (data.ok) {
                statDocs.textContent = data.stats.total_documents;
                statChunks.textContent = data.stats.total_chunks;
                statLastIngest.textContent = data.stats.last_ingestion_at ? new Date(data.stats.last_ingestion_at).toLocaleString() : 'N/A';
            }
        } catch (error) {
            console.error("Failed to load stats", error);
        }
    }

    async function loadIndexedDocs() {
        try {
            const response = await fetch('/api/docs');
            if (response.ok) {
                const data = await response.json();
                if (data.ok) {
                    allDocuments = data.documents || [];
                    // Keep selected IDs that still exist
                    const validIds = new Set(allDocuments.map(d => d.document_id));
                    selectedDocumentIds = new Set(Array.from(selectedDocumentIds).filter(id => validIds.has(id)));
                    renderDocumentCards();
                    updateScopeStatus();
                    loadStats();
                }
            }
        } catch (error) {
            console.error("Failed to load indexed docs", error);
        }
    }

    refreshCorpusBtn.addEventListener('click', () => {
        loadIndexedDocs();
    });

    selectAllBtn.addEventListener('click', () => {
        allDocuments.forEach(doc => selectedDocumentIds.add(doc.document_id));
        renderDocumentCards();
        updateScopeStatus();
    });

    removeSelectedBtn.addEventListener('click', async () => {
        if (selectedDocumentIds.size === 0) return;

        const count = selectedDocumentIds.size;
        const confirmMsg = count === 1
            ? "Are you sure you want to remove the selected document?"
            : `Are you sure you want to remove the ${count} selected documents?`;

        if (!confirm(confirmMsg)) return;

        removeSelectedBtn.disabled = true;
        const idsToRemove = Array.from(selectedDocumentIds);

        for (const docId of idsToRemove) {
            try {
                const response = await fetch(`/api/docs/${docId}`, { method: 'DELETE' });
                const result = await response.json();
                if (result.ok) {
                    selectedDocumentIds.delete(docId);
                } else {
                    console.error(`Failed to delete doc ${docId}: ${result.error}`);
                }
            } catch (error) {
                console.error(`Error deleting doc ${docId}`, error);
            }
        }

        await loadIndexedDocs();
    });

    clearConfirmCheck.addEventListener('change', () => {
        clearCorpusBtn.disabled = !clearConfirmCheck.checked;
    });

    clearCorpusBtn.addEventListener('click', async () => {
        if (!clearConfirmCheck.checked) return;
        if (!confirm("PERMANENTLY CLEAR ENTIRE CORPUS? This cannot be undone.")) return;

        clearCorpusBtn.disabled = true;
        try {
            const response = await fetch('/api/docs/clear', { method: 'POST' });
            const result = await response.json();
            if (result.ok) {
                selectedDocumentIds.clear();
                clearConfirmCheck.checked = false;
                clearCorpusBtn.disabled = true;
                await loadIndexedDocs();
            } else {
                alert(`Failed to clear corpus: ${result.error}`);
                clearCorpusBtn.disabled = false;
            }
        } catch (error) {
            console.error("Error clearing corpus", error);
            clearCorpusBtn.disabled = false;
        }
    });

    clearSelectionBtn.addEventListener('click', () => {
        selectedDocumentIds.clear();
        renderDocumentCards();
        updateScopeStatus();
    });

    ingestPdfBtn.addEventListener('click', async () => {
        if (!pdfFileInput.files || pdfFileInput.files.length === 0) {
            ingestStatusArea.textContent = "No files selected.";
            return;
        }

        const files = Array.from(pdfFileInput.files);
        const total = files.length;

        ingestStatusArea.textContent = `Batch processing: 0/${total}...`;
        ingestPdfBtn.disabled = true;
        browsePdfBtn.disabled = true;
        batchResultsArea.innerHTML = '<h3>Batch ingestion results:</h3>';
        batchResultsArea.style.display = 'block';

        let batchDebugStr = `\n[INGEST BATCH]\nfiles_selected: ${total}\n`;
        const results = [];

        for (let i = 0; i < total; i++) {
            const file = files[i];
            ingestStatusArea.textContent = `Batch processing: ${i + 1}/${total} (${file.name})...`;

            const formData = new FormData();
            formData.append("file", file);

            let result;
            try {
                const response = await fetch('/api/ingest', {
                    method: 'POST',
                    body: formData
                });
                result = await response.json();
            } catch (error) {
                result = {
                    ok: false,
                    path: file.name,
                    document_name: file.name,
                    status: "failed",
                    error: "Failed to communicate with server."
                };
            }

            results.push(result);

            // UI feedback for each file
            const resultItem = document.createElement('div');
            resultItem.style.marginBottom = '4px';

            const statusIcon = document.createElement('span');
            let statusText = '';

            if (result.status === "success") {
                statusIcon.textContent = '✔ ';
                statusIcon.style.color = 'green';
                let ocrInfo = result.ocr_used ? ` (OCR used: ${result.ocr_char_count} chars, ${result.ocr_page_count} pages)` : '';
                statusText = `${result.document_name} — ${result.chunks_indexed} chunks${ocrInfo}`;
            } else if (result.status === "skipped") {
                statusIcon.textContent = 'ℹ ';
                statusIcon.style.color = 'orange';
                statusText = `${result.document_name} — Skipped (duplicate)`;
            } else {
                statusIcon.textContent = '✖ ';
                statusIcon.style.color = 'red';
                statusText = `${result.document_name} — Failed: ${result.error || "Unknown error"}`;
            }

            resultItem.appendChild(statusIcon);
            resultItem.appendChild(document.createTextNode(statusText));
            batchResultsArea.appendChild(resultItem);

            // Debug log entry
            batchDebugStr += `\n[${i + 1}] ${file.name}\nstatus: ${result.status}\n`;
            if (result.status === "success" || result.status === "skipped") {
                batchDebugStr += `chunks: ${result.chunks_indexed}\n`;
                if (result.status === "success") {
                    batchDebugStr += `ingestion_method: ${result.ingestion_method}\n`;
                    if (result.ocr_used) {
                        batchDebugStr += `ocr_char_count: ${result.ocr_char_count}\n`;
                        batchDebugStr += `ocr_page_count: ${result.ocr_page_count}\n`;
                    }
                }
                if (result.status === "skipped") batchDebugStr += `reason: duplicate\n`;
            } else {
                batchDebugStr += `error: ${result.error || "unknown"}\n`;
            }
        }

        debugOutput.textContent = batchDebugStr + "\n" + debugOutput.textContent;
        ingestStatusArea.textContent = "Batch ingestion complete.";

        // Refresh corpus panel
        await loadIndexedDocs();

        // Recommendation: Clear selection after ingestion
        pdfFileInput.value = '';
        selectedFilesContainer.innerHTML = '<span id="selected-pdf-path">No files selected.</span>';
        ingestPdfBtn.disabled = true;
        browsePdfBtn.disabled = false;
    });

    // Initialize
    loadModels();
    loadIndexedDocs();
});
