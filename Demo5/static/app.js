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
    const ingestPdfBtn = document.getElementById('ingest-pdf-btn');
    const ingestStatusArea = document.getElementById('ingest-status-area');
    const indexedDocsList = document.getElementById('indexed-docs-list');

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
                body: JSON.stringify({ model, message })
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
            debugOutput.textContent = JSON.stringify(data.debug, null, 2);

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
            selectedPdfPath.textContent = pdfFileInput.files[0].name;
            ingestPdfBtn.disabled = false;
        } else {
            selectedPdfPath.textContent = "No PDF selected.";
            ingestPdfBtn.disabled = true;
        }
    });

    async function loadIndexedDocs() {
        try {
            const response = await fetch('/api/docs');
            if (response.ok) {
                const data = await response.json();
                indexedDocsList.innerHTML = '';
                if (data.docs && data.docs.length > 0) {
                    data.docs.forEach(docId => {
                        const li = document.createElement('li');
                        li.textContent = `- ${docId}`;
                        indexedDocsList.appendChild(li);
                    });
                } else {
                    const li = document.createElement('li');
                    li.textContent = 'None';
                    indexedDocsList.appendChild(li);
                }
            }
        } catch (error) {
            console.error("Failed to load indexed docs", error);
        }
    }

    ingestPdfBtn.addEventListener('click', async () => {
        if (!pdfFileInput.files || pdfFileInput.files.length === 0) {
            ingestStatusArea.textContent = "No PDF selected.";
            return;
        }

        const file = pdfFileInput.files[0];
        ingestStatusArea.textContent = "Ingesting...";
        ingestPdfBtn.disabled = true;
        browsePdfBtn.disabled = true;

        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch('/api/ingest', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            let debugText = debugOutput.textContent;
            let currentDebug = null;
            try {
                currentDebug = JSON.parse(debugText);
            } catch (e) {
                currentDebug = { history: [] };
            }

            const debugInfo = {
                path: file.name,
                status: result.ok ? "success" : "failed",
                doc_id: result.doc_id || null,
                chunks_indexed: result.chunks_indexed || 0,
                error: result.error || "none"
            };

            const ingestDebugStr = `\n[INGEST]\npath: ${debugInfo.path}\nstatus: ${debugInfo.status}\ndoc_id: ${debugInfo.doc_id}\nchunks_indexed: ${debugInfo.chunks_indexed}\nerror: ${debugInfo.error}\n`;

            if (typeof currentDebug === 'object' && currentDebug !== null) {
                if (!currentDebug.ingestions) {
                    currentDebug.ingestions = [];
                }
                currentDebug.ingestions.push(debugInfo);
                debugOutput.textContent = JSON.stringify(currentDebug, null, 2);
            } else {
                debugOutput.textContent = ingestDebugStr + "\n" + debugOutput.textContent;
            }

            if (result.ok) {
                ingestStatusArea.textContent = `Success: Ingested ${result.doc_id} (${result.chunks_indexed} chunks)`;
                await loadIndexedDocs();
            } else {
                ingestStatusArea.textContent = result.error || "Ingestion failed.";
            }

        } catch (error) {
            ingestStatusArea.textContent = "Failed to communicate with server for ingestion.";
        } finally {
            ingestPdfBtn.disabled = false;
            browsePdfBtn.disabled = false;
        }
    });

    // Initialize
    loadModels();
    loadIndexedDocs();
});
