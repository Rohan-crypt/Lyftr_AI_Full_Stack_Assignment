import React, { useState, useEffect, useRef } from 'react';
import './App.css';

// Generate unique session id per page load (e.g. s-7f3a8b)
function generateSessionId() {
  return 's-' + Math.random().toString(36).substring(2, 8);
}

// Backend base URL: default to VITE_BACKEND_URL, localhost:8000 locally, or live Vercel backend
const DEFAULT_BACKEND_URL = import.meta.env.VITE_BACKEND_URL || (
  window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : 'https://lyftr-ai-backend-ten.vercel.app'
);

export default function App() {
  const [sessionId] = useState(() => generateSessionId());
  const [backendUrl, setBackendUrl] = useState(DEFAULT_BACKEND_URL);
  const [systemPrompt, setSystemPrompt] = useState('');
  const [inputMessage, setInputMessage] = useState('');
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [simulateFailureHeader, setSimulateFailureHeader] = useState('');
  const [healthStatus, setHealthStatus] = useState(null);
  const [showSettings, setShowSettings] = useState(false);

  const messagesEndRef = useRef(null);

  // Scroll to bottom on message updates
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  // Check health on startup
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${backendUrl}/health`);
        if (res.ok) {
          const data = await res.json();
          setHealthStatus(data);
        } else {
          setHealthStatus({ status: 'error', detail: `HTTP ${res.status}` });
        }
      } catch (err) {
        setHealthStatus({ status: 'offline', detail: err.message });
      }
    };
    checkHealth();
  }, [backendUrl]);

  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    const trimmed = inputMessage.trim();
    if (!trimmed || isLoading) return;

    // Reset input immediately per contract
    setInputMessage('');

    // Add user message to UI
    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: trimmed,
      timestamp: new Date().toLocaleTimeString()
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const headers = {
        'Content-Type': 'application/json'
      };
      if (simulateFailureHeader.trim()) {
        headers['X-Simulate-Failure'] = simulateFailureHeader.trim();
      }

      const bodyPayload = {
        session_id: sessionId,
        message: trimmed
      };
      if (systemPrompt.trim()) {
        bodyPayload.system_prompt = systemPrompt.trim();
      }

      const response = await fetch(`${backendUrl}/chat`, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(bodyPayload)
      });

      const data = await response.json();

      if (response.ok) {
        // Successful assistant response
        const assistantMsg = {
          id: Date.now() + 1,
          role: 'assistant',
          content: data.reply,
          metadata: data.metadata,
          timestamp: new Date().toLocaleTimeString()
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } else {
        // Error from backend (e.g. 422, 503)
        const errorDetail = typeof data.detail === 'string'
          ? data.detail
          : JSON.stringify(data.detail);

        const errorMsg = {
          id: Date.now() + 1,
          role: 'error',
          content: `Error (${response.status}): ${errorDetail}`,
          status: response.status,
          timestamp: new Date().toLocaleTimeString()
        };
        setMessages((prev) => [...prev, errorMsg]);
      }
    } catch (err) {
      // Network or connection error
      const errorMsg = {
        id: Date.now() + 1,
        role: 'error',
        content: `Network Error: Could not connect to backend at ${backendUrl}. ${err.message}`,
        timestamp: new Date().toLocaleTimeString()
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="chat-app">
      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <div className="logo-badge">⚡ Lyftr AI</div>
          <div className="session-tag">
            Session: <span className="session-id">{sessionId}</span>
          </div>
        </div>

        <div className="header-right">
          <div className="health-indicator">
            <span className={`status-dot ${healthStatus?.status === 'ok' ? 'online' : 'offline'}`} />
            <span className="status-label">
              {healthStatus?.status === 'ok'
                ? `Ready (${healthStatus.keys_configured} keys, cache active)`
                : 'Backend checking...'}
            </span>
          </div>

          <button
            className="settings-toggle"
            onClick={() => setShowSettings(!showSettings)}
            title="Configuration & Failover Testing"
          >
            ⚙️ Controls
          </button>
        </div>
      </header>

      {/* Settings & Failover Test Panel */}
      {showSettings && (
        <section className="settings-panel">
          <div className="settings-grid">
            <div className="setting-item">
              <label htmlFor="system-prompt-input">System Prompt (Optional):</label>
              <input
                id="system-prompt-input"
                data-testid="system-prompt-input"
                type="text"
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                placeholder="e.g. You are a concise mathematical expert."
              />
            </div>

            <div className="setting-item">
              <label htmlFor="simulate-failure">Failover Test Hook (X-Simulate-Failure):</label>
              <div className="input-with-presets">
                <input
                  id="simulate-failure"
                  type="text"
                  value={simulateFailureHeader}
                  onChange={(e) => setSimulateFailureHeader(e.target.value)}
                  placeholder="e.g. key_1=429,key_2=500 or *=429"
                />
                <div className="preset-buttons">
                  <button type="button" onClick={() => setSimulateFailureHeader('')}>Clear</button>
                  <button type="button" onClick={() => setSimulateFailureHeader('key_1=429')}>key_1=429</button>
                  <button type="button" onClick={() => setSimulateFailureHeader('key_1=500')}>key_1=500</button>
                  <button type="button" onClick={() => setSimulateFailureHeader('*=429')}>*=429 (All Fail)</button>
                </div>
              </div>
            </div>

            <div className="setting-item">
              <label htmlFor="backend-url-input">Backend URL:</label>
              <input
                id="backend-url-input"
                type="text"
                value={backendUrl}
                onChange={(e) => setBackendUrl(e.target.value)}
                placeholder="http://localhost:8000"
              />
            </div>
          </div>
        </section>
      )}

      {/* Chat Messages Body */}
      <main className="messages-container">
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">💬</div>
            <h2>Enterprise Multi-Turn LLM Chatbot</h2>
            <p>
              Features automated key failover across provider keys, persistent SQLite multi-turn context,
              and LiteLLM response caching.
            </p>
            <div className="quick-starters">
              <button onClick={() => setInputMessage('What is the capital of France?')}>
                What is the capital of France?
              </button>
              <button onClick={() => setInputMessage('Tell me a 2-sentence story about space.')}>
                Tell me a 2-sentence story about space.
              </button>
              <button onClick={() => setInputMessage('Explain quantum computing simply.')}>
                Explain quantum computing simply.
              </button>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`message-row ${msg.role}`}>
            {msg.role === 'user' && (
              <div className="user-message-bubble">
                <div className="message-text">{msg.content}</div>
                <div className="message-time">{msg.timestamp}</div>
              </div>
            )}

            {msg.role === 'assistant' && (
              <div className="assistant-message-wrapper" data-testid="assistant-message">
                <div className="assistant-header">
                  <span className="bot-name">AI Assistant</span>
                  <span
                    className={`source-badge ${msg.metadata?.resolution_source === 'LLM_CACHE' ? 'badge-cache' : 'badge-live'}`}
                    data-testid="meta-source"
                  >
                    {msg.metadata?.resolution_source}
                  </span>
                </div>

                <div className="message-text">{msg.content}</div>

                {/* Metadata Row matching exact contract requirements */}
                <div className="metadata-bar">
                  <div className="meta-item">
                    <span className="meta-label">Model:</span>
                    <span className="meta-value" data-testid="meta-model">
                      {msg.metadata?.model}
                    </span>
                  </div>

                  <div className="meta-item">
                    <span className="meta-label">Latency:</span>
                    <span className="meta-value" data-testid="meta-latency">
                      {msg.metadata?.latency_ms} ms
                    </span>
                  </div>

                  <div className="meta-item">
                    <span className="meta-label">Input Tokens:</span>
                    <span className="meta-value" data-testid="meta-input-tokens">
                      {msg.metadata?.input_tokens}
                    </span>
                  </div>

                  <div className="meta-item">
                    <span className="meta-label">Output Tokens:</span>
                    <span className="meta-value" data-testid="meta-output-tokens">
                      {msg.metadata?.output_tokens}
                    </span>
                  </div>

                  {msg.metadata?.key_id && (
                    <div className="meta-item key-badge">
                      <span className="meta-label">Key:</span>
                      <span className="meta-value">{msg.metadata.key_id}</span>
                    </div>
                  )}

                  {typeof msg.metadata?.fallback_attempts === 'number' && msg.metadata.fallback_attempts > 0 && (
                    <div className="meta-item failover-badge">
                      <span className="meta-label">Failovers:</span>
                      <span className="meta-value">{msg.metadata.fallback_attempts}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {msg.role === 'error' && (
              <div className="error-message-bubble">
                <div className="error-title">⚠️ Error Encountered</div>
                <div className="error-text">{msg.content}</div>
              </div>
            )}
          </div>
        ))}

        {isLoading && (
          <div className="message-row assistant">
            <div className="assistant-message-wrapper loading-bubble">
              <div className="loading-dots">
                <span />
                <span />
                <span />
              </div>
              <span className="loading-text">Generating response...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </main>

      {/* Input Footer */}
      <footer className="input-container">
        {simulateFailureHeader && (
          <div className="active-simulation-banner">
            Active Hook: <code>X-Simulate-Failure: {simulateFailureHeader}</code>
            <button type="button" onClick={() => setSimulateFailureHeader('')}>✕</button>
          </div>
        )}

        <form onSubmit={handleSendMessage} className="input-form">
          <textarea
            data-testid="chat-input"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your message here... (Press Enter to send, Shift+Enter for new line)"
            rows={1}
            disabled={isLoading}
          />

          <button
            type="submit"
            data-testid="send-button"
            className="send-button"
            disabled={isLoading || !inputMessage.trim()}
          >
            {isLoading ? '...' : 'Send'}
          </button>
        </form>
      </footer>
    </div>
  );
}
