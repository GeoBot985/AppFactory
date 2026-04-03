document.addEventListener('DOMContentLoaded', () => {
    const modelSelect = document.getElementById('model-select');
    const statusArea = document.getElementById('status-area');
    const chatArea = document.getElementById('chat-area');
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const debugOutput = document.getElementById('debug-output');

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

    // Initialize
    loadModels();
});
