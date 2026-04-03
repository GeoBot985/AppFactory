document.addEventListener('DOMContentLoaded', () => {
    const modelSelect = document.getElementById('model-select');
    const statusArea = document.getElementById('status-area');
    const chatArea = document.getElementById('chat-area');
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const debugOutput = document.getElementById('debug-output');

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
    const selectAllBtn = document.getElementById('select-all-btn');
    const clearSelectionBtn = document.getElementById('clear-selection-btn');
    const retrievalScopeText = document.getElementById('retrieval-scope-text');

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

            const chunks = payload.retrieval_chunks || [];
            output += `Retrieved chunks count:\n${chunks.length}\n\n`;
            output += `Retrieved chunks:\n`;

            if (chunks.length === 0) {
                output += `0 results\n`;
            } else {
                chunks.forEach((chunk, index) => {
                    const truncatedChunk = chunk.length > 500 ? chunk.substring(0, 500) + '...' : chunk;
                    output += `\n[${index + 1}] length=${chunk.length}\n${truncatedChunk}\n`;
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
            selectedFilesContainer.innerHTML = '<span id="selected-pdf-path">No PDF selected.</span>';
            ingestPdfBtn.disabled = true;
        }
    });

    function updateScopeStatus() {
        if (selectedDocumentIds.size === 0) {
            retrievalScopeText.textContent = "Full corpus";
        } else {
            retrievalScopeText.textContent = `Working set (${selectedDocumentIds.size} documents)`;
        }
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

            const meta = document.createElement('div');
            meta.className = 'doc-meta';
            const date = new Date(doc.ingested_at).toLocaleString();
            const sizeKB = (doc.file_size_bytes / 1024).toFixed(1);
            meta.innerHTML = `
                Ingested: ${date}<br>
                Chunks: ${doc.chunk_count} | Size: ${sizeKB} KB
            `;

            card.appendChild(name);
            card.appendChild(meta);

            card.addEventListener('click', () => toggleDocumentSelection(doc.document_id));
            corpusList.appendChild(card);
        });
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
                }
            }
        } catch (error) {
            console.error("Failed to load indexed docs", error);
        }
    }

    selectAllBtn.addEventListener('click', () => {
        allDocuments.forEach(doc => selectedDocumentIds.add(doc.document_id));
        renderDocumentCards();
        updateScopeStatus();
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
                statusText = `${result.document_name} — ${result.chunks_indexed} chunks`;
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
        selectedFilesContainer.innerHTML = '<span id="selected-pdf-path">No PDF selected.</span>';
        ingestPdfBtn.disabled = true;
        browsePdfBtn.disabled = false;
    });

    // Initialize
    loadModels();
    loadIndexedDocs();
});
