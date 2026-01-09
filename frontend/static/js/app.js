// =====================================================
// ActionSync - Meeting to Jira
// =====================================================

const API_BASE = '/api';

const state = {
    user: null,
    token: localStorage.getItem('token'),
    jiraConfig: null,
    projects: [],
    selectedProject: null,
    isProcessing: false,
    ws: null,
    mode: 'meeting',
    lastResult: null,
    pendingActions: [],  // Queue of pending Jira actions (for parallel tool calls)
    actions: [],
    logs: [],  // Store console logs for display after processing
    sessionId: null,  // Current conversation session ID
    conversationMessages: [],  // Array of {role: 'user'|'assistant', content: string}
    // History state
    meetings: [],
    meetingsLoading: false,
    selectedMeeting: null,
    searchQuery: '',
    searchResults: [],
    searchLoading: false,
    // Work mode state
    workMode: 'kanban',  // 'kanban' or 'detail' or 'working'
    workStatuses: [],
    workTickets: [],
    workTicketsLoading: false,
    selectedTicket: null,
    selectedTicketLoading: false,
    // Live Ask state
    liveAsk: {
        enabled: false,
        status: 'idle', // 'idle' | 'loading' | 'listening' | 'transcribing' | 'processing'
        modelLoaded: false,
        modelLoading: false,
        modelProgress: 0,
        lastTranscription: '',
        error: null,
    },
};

// Live Ask controller instance (lazy loaded)
let liveAskController = null;

// =====================================================
// API Client
// =====================================================

async function api(endpoint, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (state.token) headers['Authorization'] = `Bearer ${state.token}`;

    const response = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });

    if (response.status === 401) { logout(); throw new Error('Session expired'); }
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'An error occurred' }));
        throw new Error(error.detail || 'An error occurred');
    }
    if (response.status === 204) return null;
    return response.json();
}

// =====================================================
// Auth Functions
// =====================================================

async function register(email, password, fullName) {
    return await api('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email, password, full_name: fullName })
    });
}

async function login(email, password) {
    const data = await api('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password })
    });
    state.token = data.access_token;
    localStorage.setItem('token', state.token);
    await loadUserData();
    return data;
}

function logout() {
    state.token = null;
    state.user = null;
    state.jiraConfig = null;
    state.projects = [];
    localStorage.removeItem('token');
    if (state.ws) { state.ws.close(); state.ws = null; }
    navigate('/login');
}

async function loadUserData() {
    try {
        state.user = await api('/auth/me');
        state.jiraConfig = await api('/jira/config');
        state.projects = await api('/jira/projects');
        if (state.projects.length > 0 && !state.selectedProject) {
            const defaultProject = state.projects.find(p => p.is_default);
            state.selectedProject = defaultProject ? defaultProject.project_key : state.projects[0].project_key;
        }
        const status = await api('/processing/status');
        state.isProcessing = status.is_processing && status.is_mine;
        connectWebSocket();
    } catch (e) {
        console.error('Failed to load user data:', e);
    }
}

// =====================================================
// Jira Config Functions
// =====================================================

async function saveJiraConfig(config) {
    if (state.jiraConfig) {
        state.jiraConfig = await api('/jira/config', { method: 'PUT', body: JSON.stringify(config) });
    } else {
        state.jiraConfig = await api('/jira/config', { method: 'POST', body: JSON.stringify(config) });
    }
    return state.jiraConfig;
}

async function addProject(projectKey, projectName, isDefault) {
    const project = await api('/jira/projects', {
        method: 'POST',
        body: JSON.stringify({ project_key: projectKey, project_name: projectName, is_default: isDefault })
    });
    state.projects.push(project);
    if (!state.selectedProject) state.selectedProject = project.project_key;
    return project;
}

async function removeProject(projectId) {
    await api(`/jira/projects/${projectId}`, { method: 'DELETE' });
    state.projects = state.projects.filter(p => p.id !== projectId);
    if (state.projects.length > 0 && !state.projects.find(p => p.project_key === state.selectedProject)) {
        state.selectedProject = state.projects[0].project_key;
    }
}

async function updateProject(projectId, data) {
    const updatedProject = await api(`/jira/projects/${projectId}`, {
        method: 'PUT',
        body: JSON.stringify(data)
    });
    const index = state.projects.findIndex(p => p.id === projectId);
    if (index >= 0) {
        state.projects[index] = updatedProject;
    }
    return updatedProject;
}

// =====================================================
// Meetings History Functions
// =====================================================

async function loadMeetings(projectKey = null) {
    state.meetingsLoading = true;
    render();
    try {
        const params = new URLSearchParams();
        if (projectKey) params.append('project_key', projectKey);
        const data = await api(`/meetings?${params.toString()}`);
        state.meetings = data.meetings || [];
    } catch (e) {
        console.error('Failed to load meetings:', e);
        state.meetings = [];
    }
    state.meetingsLoading = false;
    render();
}

async function loadMeetingDetail(meetingId) {
    try {
        state.selectedMeeting = await api(`/meetings/${meetingId}`);
        render();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

async function searchMeetings(query, projectKey = null) {
    if (!query.trim()) {
        state.searchResults = [];
        render();
        return;
    }
    state.searchLoading = true;
    render();
    try {
        const params = new URLSearchParams({ query });
        if (projectKey) params.append('project_key', projectKey);
        const data = await api(`/meetings/search?${params.toString()}`, { method: 'POST' });
        state.searchResults = data.results || [];
    } catch (e) {
        console.error('Search failed:', e);
        state.searchResults = [];
    }
    state.searchLoading = false;
    render();
}

async function deleteMeeting(meetingId) {
    if (!confirm('Are you sure you want to delete this meeting? This cannot be undone.')) {
        return;
    }
    try {
        await api(`/meetings/${meetingId}`, { method: 'DELETE' });
        showToast('Meeting deleted', 'success');
        // Clear selection if this was the selected meeting
        if (state.selectedMeeting?.id === meetingId) {
            state.selectedMeeting = null;
        }
        // Reload meetings list
        await loadMeetings();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

// =====================================================
// Work Mode Functions
// =====================================================

async function loadWorkflowStatuses(projectKey) {
    try {
        const data = await api(`/jira/workflow/${projectKey}`);
        state.workStatuses = data.statuses || [];
    } catch (e) {
        console.error('Failed to load workflow:', e);
        state.workStatuses = [];
    }
}

async function loadKanbanTickets(projectKey) {
    state.workTicketsLoading = true;
    render();
    try {
        const data = await api(`/jira/kanban/${projectKey}`);
        state.workTickets = data.issues || [];
    } catch (e) {
        console.error('Failed to load tickets:', e);
        showToast(e.message, 'error');
        state.workTickets = [];
    }
    state.workTicketsLoading = false;
    render();
}

async function loadTicketDetails(issueKey) {
    state.selectedTicketLoading = true;
    state.workMode = 'detail';
    render();
    try {
        state.selectedTicket = await api(`/jira/ticket/${issueKey}`);
    } catch (e) {
        showToast(e.message, 'error');
        state.selectedTicket = null;
        state.workMode = 'kanban';
    }
    state.selectedTicketLoading = false;
    render();
}

async function startWork(projectId, issueKey) {
    if (state.isProcessing) {
        showToast('Another task is processing', 'error');
        return;
    }

    state.isProcessing = true;
    state.workMode = 'working';
    state.logs = [];
    state.lastResult = null;
    render();

    try {
        await api('/work/start', {
            method: 'POST',
            body: JSON.stringify({ project_id: projectId, issue_key: issueKey })
        });
    } catch (e) {
        state.isProcessing = false;
        state.workMode = 'detail';
        showToast(e.message, 'error');
        render();
    }
}

// =====================================================
// Processing Functions
// =====================================================

async function processMeeting(transcription, projectKey) {
    state.isProcessing = true;
    state.actions = [];
    state.pendingActions = [];
    state.lastResult = null;
    state.logs = [];
    render();
    await api('/meetings/process', {
        method: 'POST',
        body: JSON.stringify({ transcription, project_key: projectKey })
    });
}

async function askQuestion(question, projectKey, isFollowUp = false) {
    state.isProcessing = true;
    state.actions = [];
    state.pendingActions = [];
    state.logs = [];

    // For new questions, clear the session and conversation
    if (!isFollowUp) {
        state.sessionId = null;
        state.conversationMessages = [];
        state.lastResult = null;
    }

    // Add user message to conversation
    state.conversationMessages.push({ role: 'user', content: question });

    render();
    await api('/jira/ask', {
        method: 'POST',
        body: JSON.stringify({
            question,
            project_key: projectKey,
            session_id: isFollowUp ? state.sessionId : null
        })
    });
}

async function abortProcessing() {
    try {
        await api('/processing/abort', { method: 'POST' });
    } catch (e) {
        showToast(e.message, 'error');
    }
}

// =====================================================
// Live Ask Mode
// =====================================================

async function initLiveAsk() {
    if (liveAskController) return liveAskController;

    // Dynamically import the controller
    const { LiveAskController } = await import('/static/js/live-ask/live-ask-controller.js');

    liveAskController = new LiveAskController({
        onStatusChange: (status) => {
            state.liveAsk.status = status;
            render();
        },
        onModelProgress: (progress) => {
            state.liveAsk.modelProgress = progress.progress;
            state.liveAsk.modelLoading = progress.status === 'downloading';
            state.liveAsk.modelLoaded = progress.status === 'ready';
            render();
        },
        onTranscription: (text) => {
            state.liveAsk.lastTranscription = text;
            console.log('Live Ask transcription:', text);
            render();
        },
        onError: (error) => {
            state.liveAsk.error = error?.message || String(error);
            showToast(`Live Ask error: ${state.liveAsk.error}`, 'error');
            render();
        },
    });

    // Set the handler to call askQuestion
    liveAskController.setAskQuestionHandler(async (question) => {
        if (!state.selectedProject) {
            showToast('Please select a project first', 'error');
            return;
        }

        // Check if this is a follow-up (we have an existing result with a session)
        const isFollowUp = state.lastResult && state.sessionId;

        if (!isFollowUp) {
            // New question - switch to question mode
            state.mode = 'question';
            render();
            // Small delay to let render complete
            await new Promise(r => setTimeout(r, 100));
            const inputEl = document.getElementById('input-text');
            if (inputEl) inputEl.value = question;
        }

        // Submit the question
        await askQuestion(question, state.selectedProject, isFollowUp);
    });

    return liveAskController;
}

// Click to start/stop recording
async function toggleLiveAskRecording() {
    try {
        const controller = await initLiveAsk();

        // If already recording, stop
        if (state.liveAsk.status === 'recording') {
            await controller.stopRecording();
            return;
        }

        // Check prerequisites
        if (!state.selectedProject) {
            showToast('Please select a project first', 'error');
            return;
        }

        // Check browser support
        const { LiveAskController } = await import('/static/js/live-ask/live-ask-controller.js');
        const supportInfo = LiveAskController.getSupportInfo();

        if (!supportInfo.isSupported) {
            showToast(`Live Ask not supported: ${supportInfo.reason}`, 'error');
            return;
        }

        // Start recording
        state.liveAsk.lastTranscription = '';
        state.liveAsk.error = null;
        await controller.startRecording();

    } catch (error) {
        const errorMsg = error?.message || String(error);
        state.liveAsk.error = errorMsg;
        showToast(`Live Ask error: ${errorMsg}`, 'error');
        console.error('Live Ask error:', error);
        render();
    }
}

// Make function available globally
window.toggleLiveAskRecording = toggleLiveAskRecording;

function renderLiveAskButton() {
    const { status, modelProgress } = state.liveAsk;
    const isLoading = status === 'loading';
    const isRecording = status === 'recording';
    const isTranscribing = status === 'transcribing';
    const isProcessing = status === 'processing';
    const isBusy = isLoading || isTranscribing || isProcessing;

    let buttonText = 'Voice';
    let statusClass = status || 'idle';

    if (isLoading) {
        buttonText = `Loading ${modelProgress}%`;
    } else if (isRecording) {
        buttonText = 'Stop';
    } else if (isTranscribing) {
        buttonText = 'Transcribing...';
    } else if (isProcessing) {
        buttonText = 'Processing...';
    }

    return `
        <button class="btn btn-lg live-ask-btn ${statusClass}"
                onclick="toggleLiveAskRecording()"
                ${isBusy || state.isProcessing ? 'disabled' : ''}>
            <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"/>
            </svg>
            ${buttonText}
        </button>
    `;
}

function renderLiveAskTranscription() {
    const { status, lastTranscription, error } = state.liveAsk;

    // Show when recording, processing, or has recent transcription
    const isActive = ['loading', 'recording', 'transcribing', 'processing'].includes(status);
    if (!isActive && !lastTranscription && !error) return '';

    const statusText = {
        'idle': 'Ready',
        'loading': 'Loading model...',
        'recording': 'Recording...',
        'transcribing': 'Transcribing...',
        'processing': 'Processing question...',
    }[status] || '';

    let content = '';
    if (error) {
        content = `<div class="live-ask-transcription-text error">Error: ${escapeHtml(error)}</div>`;
    } else if (lastTranscription) {
        content = `<div class="live-ask-transcription-text">"${escapeHtml(lastTranscription)}"</div>`;
    } else if (status === 'loading') {
        content = `<div class="live-ask-transcription-text muted">Loading Whisper model (first time may take a minute)...</div>`;
    } else if (status === 'recording') {
        content = `<div class="live-ask-transcription-text muted">Listening... Click mic button to stop.</div>`;
    } else if (status === 'transcribing') {
        content = `<div class="live-ask-transcription-text muted">Transcribing your question...</div>`;
    } else if (status === 'processing') {
        content = `<div class="live-ask-transcription-text muted">Asking Claude...</div>`;
    }

    return `
        <div class="live-ask-transcription">
            <div class="live-ask-transcription-header">
                <span class="live-ask-status-indicator ${status}"></span>
                <span>${statusText}</span>
            </div>
            ${content}
        </div>
    `;
}

// =====================================================
// WebSocket
// =====================================================

function connectWebSocket() {
    if (state.ws) return;
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    state.ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws?token=${state.token}`);

    state.ws.onmessage = (event) => {
        if (event.data === 'pong') return;
        try {
            handleWsMessage(JSON.parse(event.data));
        } catch (e) {
            console.warn('Failed to parse message:', event.data);
        }
    };

    state.ws.onclose = () => {
        state.ws = null;
        setTimeout(() => { if (state.token) connectWebSocket(); }, 5000);
    };

    setInterval(() => {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send('ping');
    }, 30000);
}

function handleWsMessage(data) {
    const consoleBody = document.getElementById('console-output');

    if (data.type === 'complete' || data.type === 'error' || data.type === 'aborted') {
        state.isProcessing = false;
        state.pendingActions = [];

        if (data.type === 'complete' && data.success) {
            const answerContent = state.mode === 'question' ? data.answer : data.summary;

            // Add assistant message to conversation
            if (state.mode === 'question' && answerContent) {
                state.conversationMessages.push({ role: 'assistant', content: answerContent });
            }

            state.lastResult = {
                mode: state.mode,
                content: answerContent,
                actions: [...state.actions],
                logs: [...state.logs],
                success: true
            };

            // Store session_id for follow-up questions
            if (state.mode === 'question' && data.session_id) {
                state.sessionId = data.session_id;
            }

            showToast(state.mode === 'question' ? 'Answer ready' : 'Processing complete', 'success');
        } else if (data.type === 'aborted') {
            state.lastResult = null;
            // Remove the last user message if aborted
            if (state.conversationMessages.length > 0 && state.conversationMessages[state.conversationMessages.length - 1].role === 'user') {
                state.conversationMessages.pop();
            }
            showToast('Aborted', 'info');
        } else {
            state.lastResult = {
                mode: state.mode,
                error: data.error,
                logs: [...state.logs],
                success: false
            };
            // Remove the last user message on error
            if (state.conversationMessages.length > 0 && state.conversationMessages[state.conversationMessages.length - 1].role === 'user') {
                state.conversationMessages.pop();
            }
            showToast(data.error || 'Failed', 'error');
        }
        render();
        return;
    }

    // Track actions using a queue to handle parallel tool calls
    if (data.type === 'tool_use') {
        const toolName = data.tool || '';
        const input = data.input || {};
        if (toolName.includes('create_issue') || toolName.includes('update_issue') ||
            toolName.includes('add_comment') || toolName.includes('transition_issue')) {
            state.pendingActions.push({ tool: toolName, input: input });
        }
    }

    if (data.type === 'tool_result' && state.pendingActions.length > 0) {
        const result = data.content || '';
        // Check if this result looks like it's from a Jira action (has issue key or is an error)
        const keyMatch = result.match(/([A-Z]+-\d+)/);
        const looksLikeJiraResult = keyMatch || result.toLowerCase().includes('issue') ||
            result.toLowerCase().includes('error') || result.toLowerCase().includes('created') ||
            result.toLowerCase().includes('updated');

        if (looksLikeJiraResult) {
            const pendingAction = state.pendingActions.shift(); // FIFO - first in, first out
            if (pendingAction) {
                const action = { ...pendingAction, result };
                if (keyMatch) action.issueKey = keyMatch[1];
                // Check if the result indicates an error
                const isError = data.is_error || result.toLowerCase().includes('error') || result.toLowerCase().includes('failed');
                action.isError = isError;
                state.actions.push(action);
            }
        }
    }

    // ALWAYS save logs to state (even if console not visible)
    let logEntry = null;
    if (data.type === 'text') {
        logEntry = { type: 'text', content: data.content || '' };
    } else if (data.type === 'tool_use') {
        logEntry = { type: 'tool_use', tool: data.tool || '', input: data.input };
    } else if (data.type === 'tool_result') {
        const content = data.content || '';
        const isError = data.is_error || content.toLowerCase().includes('error') || content.toLowerCase().includes('failed');
        logEntry = { type: 'tool_result', content: content, isError: isError };
    }
    if (logEntry) {
        state.logs.push(logEntry);
    }

    // Update live console if visible
    if (!consoleBody) return;

    const line = document.createElement('div');
    line.className = 'console-line';

    if (data.type === 'text') {
        line.innerHTML = `<span class="console-prompt">></span><span class="console-text">${escapeHtml(data.content || '')}</span>`;
    } else if (data.type === 'tool_use') {
        const toolName = data.tool || '';
        const inputStr = data.input ? JSON.stringify(data.input, null, 2) : '';
        line.innerHTML = `<span class="console-prompt">$</span><span class="console-text tool">${escapeHtml(toolName)}</span>`;
        if (inputStr) {
            const inputLine = document.createElement('div');
            inputLine.className = 'console-line';
            inputLine.innerHTML = `<pre class="console-input">${escapeHtml(inputStr)}</pre>`;
            consoleBody.appendChild(line);
            consoleBody.appendChild(inputLine);
            consoleBody.scrollTop = consoleBody.scrollHeight;
            return;
        }
    } else if (data.type === 'tool_result') {
        const content = data.content || '';
        const isError = data.is_error || content.toLowerCase().includes('error') || content.toLowerCase().includes('failed');
        line.innerHTML = `<span class="console-prompt">${isError ? '!' : '<'}</span><span class="console-text ${isError ? 'error' : 'result'}">${escapeHtml(content)}</span>`;
    }

    consoleBody.appendChild(line);
    consoleBody.scrollTop = consoleBody.scrollHeight;
}

// =====================================================
// Router
// =====================================================

function navigate(path) {
    window.history.pushState({}, '', path);
    render();
}

function getCurrentPath() {
    return window.location.pathname;
}

// =====================================================
// Render Functions
// =====================================================

function renderLoginPage() {
    return `
        <div class="auth-container">
            <div class="auth-card">
                <div class="auth-brand">
                    <div class="auth-logo">
                        <div class="auth-logo-mark">A</div>
                        <span class="auth-logo-text">Action<span>Sync</span></span>
                    </div>
                    <h1 class="auth-title">Welcome back</h1>
                    <p class="auth-subtitle">Sign in to your command center</p>
                </div>
                <form class="auth-form" id="login-form">
                    <div id="login-error" class="alert alert-error hidden"></div>
                    <div class="form-group">
                        <label class="form-label">Email</label>
                        <input type="email" id="email" class="form-input" placeholder="you@company.com" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Password</label>
                        <input type="password" id="password" class="form-input" placeholder="Enter password" required>
                    </div>
                    <button type="submit" class="btn btn-primary btn-block btn-lg">Sign In</button>
                </form>
                <div class="auth-footer">
                    New here? <a href="/register" onclick="event.preventDefault(); navigate('/register')">Create account</a>
                </div>
            </div>
        </div>
    `;
}

function renderRegisterPage() {
    return `
        <div class="auth-container">
            <div class="auth-card">
                <div class="auth-brand">
                    <div class="auth-logo">
                        <div class="auth-logo-mark">A</div>
                        <span class="auth-logo-text">Action<span>Sync</span></span>
                    </div>
                    <h1 class="auth-title">Get started</h1>
                    <p class="auth-subtitle">Create your account</p>
                </div>
                <form class="auth-form" id="register-form">
                    <div id="register-error" class="alert alert-error hidden"></div>
                    <div class="form-group">
                        <label class="form-label">Full Name</label>
                        <input type="text" id="fullName" class="form-input" placeholder="John Doe">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Email</label>
                        <input type="email" id="email" class="form-input" placeholder="you@company.com" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Password</label>
                        <input type="password" id="password" class="form-input" placeholder="Min 6 characters" required minlength="6">
                    </div>
                    <button type="submit" class="btn btn-primary btn-block btn-lg">Create Account</button>
                </form>
                <div class="auth-footer">
                    Already have an account? <a href="/login" onclick="event.preventDefault(); navigate('/login')">Sign in</a>
                </div>
            </div>
        </div>
    `;
}

function renderHeader() {
    const initials = state.user?.full_name
        ? state.user.full_name.split(' ').map(n => n[0]).join('').toUpperCase()
        : state.user?.email?.[0]?.toUpperCase() || '?';

    const path = getCurrentPath();
    const isSettings = path === '/settings';
    const isHistory = path === '/history';
    const hasEmbeddingsEnabled = state.projects.some(p => p.embeddings_enabled);

    return `
        <header class="app-header">
            <div class="header-left">
                <a href="/" class="header-logo" onclick="event.preventDefault(); navigate('/')">
                    <div class="header-logo-mark">A</div>
                    <span class="header-logo-text">Action<span>Sync</span></span>
                </a>
            </div>

            <nav class="header-nav">
                <a href="/" class="header-nav-link ${!isSettings && !isHistory ? 'active' : ''}" onclick="event.preventDefault(); navigate('/')">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
                    Command
                </a>
                ${hasEmbeddingsEnabled ? `
                <a href="/history" class="header-nav-link ${isHistory ? 'active' : ''}" onclick="event.preventDefault(); navigate('/history'); loadMeetings();">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    History <span class="beta-badge-nav">BETA</span>
                </a>
                ` : ''}
                <a href="/settings" class="header-nav-link ${isSettings ? 'active' : ''}" onclick="event.preventDefault(); navigate('/settings')">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                    Settings
                </a>
            </nav>

            <div class="header-right">
                <div class="header-user">
                    <div class="user-avatar">${initials}</div>
                    <span class="user-name-header">${escapeHtml(state.user?.full_name || 'User')}</span>
                </div>
                <button class="btn btn-ghost btn-sm" onclick="logout()" title="Sign out">
                    <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>
                    </svg>
                </button>
            </div>
        </header>
    `;
}

function renderFollowUpInput() {
    return `
        <div class="follow-up-input">
            <div class="follow-up-container">
                <input
                    type="text"
                    id="follow-up-text"
                    class="follow-up-field"
                    placeholder="Ask a follow-up question..."
                    onkeydown="if(event.key === 'Enter') handleFollowUp()"
                />
                <div class="follow-up-actions">
                    ${renderLiveAskButton()}
                    <button class="btn btn-primary" onclick="handleFollowUp()">
                        <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/>
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    `;
}

function handleFollowUp() {
    const input = document.getElementById('follow-up-text')?.value.trim();
    if (!input || !state.selectedProject) return;
    // Always true for follow-up since we're in the follow-up UI
    askQuestion(input, state.selectedProject, true);
}

window.handleFollowUp = handleFollowUp;

function renderInputPanel() {
    const isMeetingMode = state.mode === 'meeting';
    const isQuestionMode = state.mode === 'question';
    const isWorkMode = state.mode === 'work';

    const projectPills = state.projects.map(p => `
        <button class="project-pill ${state.selectedProject === p.project_key ? 'active' : ''}"
                onclick="selectProject('${p.project_key}')">
            ${escapeHtml(p.project_key)}
        </button>
    `).join('') || '<span class="text-muted">No projects</span>';

    const inputPlaceholder = isMeetingMode
        ? 'Paste your meeting transcription here...\n\nExample:\n"John: We need to fix the login bug by Friday"\n"Sarah: I\'ll create a ticket for the new dashboard feature"'
        : 'Ask anything about your Jira project...\n\nExamples:\n- What are the open bugs?\n- Show me tasks assigned to me\n- What\'s the status of PROJECT-123?';

    return `
        <div class="input-panel-centered">
            <div class="input-panel-header">
                <h1 class="input-panel-title">${isMeetingMode ? 'Process Meeting' : isWorkMode ? 'Work Mode' : 'Ask Question'}</h1>
                <p class="input-panel-subtitle">${isMeetingMode ? 'Paste your meeting transcription to create Jira tickets' : isWorkMode ? 'Select a ticket to start working on' : 'Ask anything about your Jira project'}</p>
            </div>

            <div class="mode-selector-centered">
                <button class="mode-btn ${isMeetingMode ? 'active' : ''}" onclick="setMode('meeting')">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
                    Meeting
                </button>
                <button class="mode-btn ${isQuestionMode ? 'active' : ''}" onclick="setMode('question')">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    Ask
                </button>
                <button class="mode-btn ${isWorkMode ? 'active' : ''}" onclick="setMode('work')">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"/></svg>
                    Work
                </button>
            </div>

            <div class="project-selector-centered">
                <div class="section-label">Project</div>
                <div class="project-grid">${projectPills}</div>
            </div>

            <div class="input-area-centered">
                <textarea
                    id="input-text"
                    class="input-textarea-centered"
                    placeholder="${inputPlaceholder}"
                ></textarea>
                <div class="input-actions-centered">
                    ${isQuestionMode ? renderLiveAskButton() : ''}
                    <button
                        class="btn btn-primary btn-lg"
                        onclick="handleSubmit()"
                        ${!state.selectedProject || !state.jiraConfig ? 'disabled' : ''}
                    >
                        ${isMeetingMode ? 'Process Meeting' : 'Ask Question'}
                    </button>
                </div>
            </div>
        </div>
    `;
}

function renderOutputStage() {
    if (!state.jiraConfig) {
        return `
            <main class="output-stage">
                <div class="empty-stage">
                    <div class="empty-icon">
                        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                    </div>
                    <h2 class="empty-title">Configure Jira</h2>
                    <p class="empty-description">Connect your Jira account to start processing meetings and asking questions.</p>
                    <button class="btn btn-primary" onclick="navigate('/settings')" style="margin-top: 24px">Go to Settings</button>
                </div>
            </main>
        `;
    }

    if (state.projects.length === 0) {
        return `
            <main class="output-stage">
                <div class="empty-stage">
                    <div class="empty-icon">
                        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
                    </div>
                    <h2 class="empty-title">Add a Project</h2>
                    <p class="empty-description">Add at least one Jira project to start processing meetings.</p>
                    <button class="btn btn-primary" onclick="navigate('/settings')" style="margin-top: 24px">Add Project</button>
                </div>
            </main>
        `;
    }

    // Show processing view
    if (state.isProcessing) {
        return `
            <main class="output-stage">
                <div class="status-bar">
                    <div class="status-indicator">
                        <div class="status-dot active"></div>
                        <span class="status-text">${state.mode === 'meeting' ? 'Processing meeting...' : 'Searching...'}</span>
                    </div>
                    <div class="status-actions">
                        <button class="btn btn-danger btn-sm" onclick="handleAbort()">
                            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                            Stop
                        </button>
                    </div>
                </div>
                <div class="live-console">
                    <div class="console-header">
                        <div class="console-dots">
                            <div class="console-dot red"></div>
                            <div class="console-dot yellow"></div>
                            <div class="console-dot green"></div>
                        </div>
                        <span class="console-title">live output</span>
                    </div>
                    <div class="console-body" id="console-output">
                        <div class="console-line">
                            <span class="console-prompt">></span>
                            <span class="console-text thinking">Initializing...</span>
                        </div>
                    </div>
                </div>
            </main>
        `;
    }

    // Show results view
    if (state.lastResult) {
        const isQuestionMode = state.mode === 'question';
        return `
            <main class="output-stage">
                <div class="status-bar">
                    <div class="status-indicator">
                        <div class="status-dot ${state.lastResult.success ? 'success' : 'error'}"></div>
                        <span class="status-text">${state.lastResult.success ? 'Complete' : 'Error'}</span>
                    </div>
                    <div class="status-actions">
                        <button class="btn btn-primary btn-sm" onclick="clearResult()">
                            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
                            New
                        </button>
                    </div>
                </div>
                ${renderResultsPanel()}
                ${isQuestionMode ? renderFollowUpInput() : ''}
            </main>
        `;
    }

    // Show work mode views
    if (state.mode === 'work') {
        let mainContent;
        if (state.workMode === 'kanban') {
            mainContent = renderKanban();
        } else if (state.workMode === 'detail') {
            mainContent = renderTicketDetail();
        } else if (state.workMode === 'working') {
            mainContent = renderProcessingConsole();
        }
        return `
            <main class="output-stage work-mode">
                <div class="work-header">
                    <div class="mode-selector-centered">
                        <button class="mode-btn" onclick="setMode('meeting')">
                            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
                            Meeting
                        </button>
                        <button class="mode-btn" onclick="setMode('question')">
                            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                            Ask
                        </button>
                        <button class="mode-btn active" onclick="setMode('work')">
                            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"/></svg>
                            Work
                        </button>
                    </div>
                    <div class="project-selector-centered">
                        <div class="section-label">Project</div>
                        <div class="project-grid">
                            ${state.projects.map(p => `
                                <button class="project-pill ${state.selectedProject === p.project_key ? 'active' : ''}"
                                        onclick="selectProject('${p.project_key}'); setMode('work');">
                                    ${escapeHtml(p.project_key)}
                                </button>
                            `).join('') || '<span class="text-muted">No projects</span>'}
                        </div>
                    </div>
                </div>
                ${mainContent}
            </main>
        `;
    }

    // Show input panel (centered)
    return `
        <main class="output-stage">
            ${renderInputPanel()}
        </main>
    `;
}

function renderResultsPanel() {
    const result = state.lastResult;
    const hasActions = result.actions && result.actions.length > 0;
    const activeTab = state.resultsTab || 'output';
    const isQuestionMode = state.mode === 'question';
    const hasConversation = isQuestionMode && state.conversationMessages.length > 0;

    return `
        <div class="results-panel">
            <div class="results-tabs">
                <button class="results-tab ${activeTab === 'output' ? 'active' : ''}" onclick="setResultsTab('output')">
                    Output
                </button>
                ${hasActions ? `
                    <button class="results-tab ${activeTab === 'actions' ? 'active' : ''}" onclick="setResultsTab('actions')">
                        Actions <span class="tab-badge">${result.actions.length}</span>
                    </button>
                ` : ''}
            </div>
            <div class="results-content">
                ${activeTab === 'output' ? `
                    <div class="output-content ${hasConversation ? 'conversation-view' : ''}">
                        ${hasConversation ? renderConversation() : (
                            result.success ? formatContent(result.content || 'Done') : `<span style="color: var(--error)">${escapeHtml(result.error || 'An error occurred')}</span>`
                        )}
                    </div>
                ` : `
                    <div class="actions-content">
                        ${result.actions.map(renderActionCard).join('')}
                    </div>
                `}
            </div>
        </div>
    `;
}

function renderConversation() {
    return state.conversationMessages.map(msg => `
        <div class="conversation-message ${msg.role}">
            <div class="message-role">${msg.role === 'user' ? 'You' : 'ActionSync'}</div>
            <div class="message-content">${msg.role === 'user' ? escapeHtml(msg.content) : formatContent(msg.content)}</div>
        </div>
    `).join('');
}

function setResultsTab(tab) {
    state.resultsTab = tab;
    render();
}

function renderLogEntry(log) {
    if (log.type === 'text') {
        return `<div class="log-entry"><span class="log-prompt">></span><span class="log-text">${escapeHtml(log.content)}</span></div>`;
    } else if (log.type === 'tool_use') {
        const inputStr = log.input ? JSON.stringify(log.input, null, 2) : '';
        return `
            <div class="log-entry tool-use">
                <span class="log-prompt">$</span>
                <span class="log-tool">${escapeHtml(log.tool)}</span>
                ${inputStr ? `<pre class="log-input">${escapeHtml(inputStr)}</pre>` : ''}
            </div>
        `;
    } else if (log.type === 'tool_result') {
        const className = log.isError ? 'log-result error' : 'log-result';
        return `
            <div class="log-entry tool-result">
                <span class="log-prompt">${log.isError ? '!' : '<'}</span>
                <pre class="${className}">${escapeHtml(log.content)}</pre>
            </div>
        `;
    }
    return '';
}

function renderActionCard(action) {
    const toolName = action.tool || '';
    const input = action.input || {};
    const isError = action.isError;
    let type = 'action', icon = '⚡', label = 'Action', summary = '';

    if (toolName.includes('create_issue')) {
        type = isError ? 'error' : 'created';
        icon = isError ? '❌' : '✨';
        label = isError ? 'Failed to Create' : 'Created';
        summary = input.summary || 'New issue';
    } else if (toolName.includes('update_issue')) {
        type = isError ? 'error' : 'updated';
        icon = isError ? '❌' : '✏️';
        label = isError ? 'Failed to Update' : 'Updated';
        summary = input.summary || 'Updated issue';
    } else if (toolName.includes('add_comment')) {
        type = isError ? 'error' : 'commented';
        icon = isError ? '❌' : '💬';
        label = isError ? 'Failed to Comment' : 'Commented';
        summary = truncate(input.comment || input.body || 'Added comment', 50);
    } else if (toolName.includes('transition_issue')) {
        type = isError ? 'error' : 'transitioned';
        icon = isError ? '❌' : '🔄';
        label = isError ? 'Failed to Transition' : 'Transitioned';
        summary = input.transition_name || 'Status changed';
    }

    // Show error message if there was an error
    const errorMsg = isError && action.result ? truncate(action.result, 100) : '';

    // Build ticket URL if we have the issue key and jira config
    const ticketUrl = action.issueKey && state.jiraConfig?.jira_base_url
        ? `${state.jiraConfig.jira_base_url}/browse/${action.issueKey}`
        : null;

    const cardContent = `
        <div class="action-icon">${icon}</div>
        <div class="action-content">
            <div class="action-type">${label}</div>
            <div class="action-summary">${escapeHtml(summary)}</div>
            ${errorMsg ? `<div class="action-error">${escapeHtml(errorMsg)}</div>` : ''}
        </div>
        ${action.issueKey ? `<span class="action-key">${action.issueKey}</span>` : ''}
    `;

    if (ticketUrl) {
        return `<a href="${ticketUrl}" target="_blank" class="action-card ${type}">${cardContent}</a>`;
    }
    return `<div class="action-card ${type}">${cardContent}</div>`;
}

function renderSettings() {
    const projectCards = state.projects.map(p => `
        <div class="project-card">
            <div class="project-card-header">
                <span class="project-card-key">${escapeHtml(p.project_key)}</span>
                <button class="btn btn-ghost btn-sm" onclick="handleRemoveProject(${p.id})" title="Remove project">
                    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </div>
            ${state.jiraConfig?.has_gitlab ? `
                <div class="form-group" style="margin-top: 12px;">
                    <label class="form-label form-label-sm">GitLab Projects</label>
                    <input type="text" class="form-input form-input-sm" id="gitlab-projects-${p.id}"
                        placeholder="group/repo1, group/repo2"
                        value="${escapeHtml(p.gitlab_projects || '')}"
                        onchange="handleUpdateProjectField(${p.id}, 'gitlab_projects', this.value)">
                    <span class="form-hint">Comma-separated list of GitLab project paths</span>
                </div>
            ` : ''}
            <div class="form-group" style="margin-top: 12px;">
                <label class="form-label form-label-sm">Custom Instructions</label>
                <textarea class="form-input form-input-sm" id="custom-instructions-${p.id}"
                    placeholder="Add project-specific instructions for the AI..."
                    rows="3"
                    onchange="handleUpdateProjectField(${p.id}, 'custom_instructions', this.value)">${escapeHtml(p.custom_instructions || '')}</textarea>
                <span class="form-hint">These instructions will be added to the AI prompt for this project</span>
            </div>
            <div class="form-group" style="margin-top: 12px;">
                <label class="form-label form-label-sm">Kanban JQL Filter</label>
                <input type="text" class="form-input form-input-sm" id="kanban-jql-${p.id}"
                    placeholder="e.g., status != Done AND assignee = currentUser()"
                    value="${escapeHtml(p.kanban_jql || '')}"
                    onchange="handleUpdateProjectField(${p.id}, 'kanban_jql', this.value)">
                <span class="form-hint">JQL query to filter which tickets appear on the Kanban board</span>
            </div>
            <div class="form-group" style="margin-top: 12px;">
                <label class="toggle-label">
                    <input type="checkbox" class="toggle-input" id="embeddings-${p.id}"
                        ${p.embeddings_enabled ? 'checked' : ''}
                        onchange="handleUpdateProjectField(${p.id}, 'embeddings_enabled', this.checked)">
                    <span class="toggle-switch"></span>
                    <span class="toggle-text">Meeting History <span class="beta-badge">BETA</span></span>
                </label>
                <span class="form-hint">Store meetings with semantic search. Access past meeting context in the History section.</span>
            </div>
        </div>
    `).join('') || '<span class="text-muted">No projects added</span>';

    return `
        ${renderHeader()}
        <main class="settings-stage">
            <div class="settings-header">
                <h1 class="settings-title">Settings</h1>
                <p class="settings-subtitle">Configure your Jira and GitLab integration</p>
            </div>

            <div class="settings-card">
                <h3 class="settings-card-title">Jira Connection</h3>
                <form id="jira-config-form">
                    <div id="config-message" class="alert hidden"></div>
                    <div class="form-group">
                        <label class="form-label">Jira Base URL</label>
                        <input type="url" id="jiraUrl" class="form-input" placeholder="https://yourcompany.atlassian.net" value="${escapeHtml(state.jiraConfig?.jira_base_url || '')}" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Email</label>
                        <input type="email" id="jiraEmail" class="form-input" placeholder="you@company.com" value="${escapeHtml(state.jiraConfig?.jira_email || '')}" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">API Token</label>
                        <input type="password" id="jiraToken" class="form-input" placeholder="${state.jiraConfig ? '••••••••' : 'Enter token'}" ${state.jiraConfig ? '' : 'required'}>
                        <span class="form-hint"><a href="https://id.atlassian.com/manage-profile/security/api-tokens" target="_blank">Get your API token</a></span>
                    </div>
                    <button type="submit" class="btn btn-primary">${state.jiraConfig ? 'Update' : 'Save'}</button>
                </form>
            </div>

            <div class="settings-card">
                <h3 class="settings-card-title">GitLab Integration</h3>
                <p class="settings-card-description">Connect GitLab to pull code context when creating tickets.</p>
                <form id="gitlab-config-form">
                    <div id="gitlab-message" class="alert hidden"></div>
                    <div class="form-group">
                        <label class="form-label">GitLab URL</label>
                        <input type="url" id="gitlabUrl" class="form-input" placeholder="https://gitlab.com" value="${escapeHtml(state.jiraConfig?.gitlab_url || '')}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Personal Access Token</label>
                        <input type="password" id="gitlabToken" class="form-input" placeholder="${state.jiraConfig?.has_gitlab ? '••••••••' : 'Enter token (optional)'}">
                        <span class="form-hint"><a href="https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html" target="_blank">Create a token</a> with read_api scope</span>
                    </div>
                    <button type="submit" class="btn btn-secondary">${state.jiraConfig?.has_gitlab ? 'Update GitLab' : 'Connect GitLab'}</button>
                </form>
            </div>

            <div class="settings-card">
                <h3 class="settings-card-title">Projects</h3>
                <div class="project-cards">${projectCards}</div>
                <form class="add-project-form" id="add-project-form">
                    <input type="text" id="projectKey" class="form-input" placeholder="PROJECT" pattern="[A-Za-z0-9_]+" required>
                    <button type="submit" class="btn btn-secondary">Add</button>
                </form>
            </div>
        </main>
    `;
}

function renderHistory() {
    const formatDate = (dateStr) => {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    };

    const meetingsList = state.meetings.map(m => `
        <div class="meeting-card ${state.selectedMeeting?.id === m.id ? 'selected' : ''}" onclick="loadMeetingDetail(${m.id})">
            <div class="meeting-card-header">
                <span class="meeting-project">${escapeHtml(m.project_key)}</span>
                <span class="meeting-date">${formatDate(m.created_at)}</span>
            </div>
            <div class="meeting-title">${escapeHtml(m.title || 'Untitled Meeting')}</div>
            ${m.tickets_created?.length ? `
                <div class="meeting-tickets">
                    ${m.tickets_created.slice(0, 3).map(t => `<span class="ticket-tag">${escapeHtml(t)}</span>`).join('')}
                    ${m.tickets_created.length > 3 ? `<span class="ticket-more">+${m.tickets_created.length - 3}</span>` : ''}
                </div>
            ` : ''}
        </div>
    `).join('') || '<div class="empty-meetings">No meetings yet. Process a meeting to see it here.</div>';

    const searchResultsList = state.searchResults.map(r => `
        <div class="search-result" onclick="loadMeetingDetail(${r.meeting_id})">
            <div class="search-result-header">
                <span class="search-project">${escapeHtml(r.project_key)}</span>
                <span class="search-similarity">${Math.round(r.similarity * 100)}% match</span>
            </div>
            <div class="search-meeting">${escapeHtml(r.meeting_title)}</div>
            <div class="search-content">${escapeHtml(truncate(r.content, 200))}</div>
        </div>
    `).join('') || (state.searchQuery ? '<div class="empty-search">No results found.</div>' : '');

    return `
        ${renderHeader()}
        <main class="history-stage">
            <div class="history-header">
                <h1 class="history-title">Meeting History</h1>
                <p class="history-subtitle">Search and browse past meetings</p>
            </div>

            <div class="search-section">
                <div class="search-input-wrap">
                    <svg class="search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
                    </svg>
                    <input type="text" class="search-input" id="meeting-search"
                        placeholder="Search meetings semantically..."
                        value="${escapeHtml(state.searchQuery)}"
                        onkeyup="handleSearchKeyup(event)">
                    ${state.searchLoading ? '<div class="search-spinner"></div>' : ''}
                </div>
            </div>

            <div class="history-content">
                <div class="history-sidebar">
                    <h3 class="sidebar-title">Recent Meetings</h3>
                    ${state.meetingsLoading ? '<div class="loading-spinner"></div>' : `
                        <div class="meetings-list">${meetingsList}</div>
                    `}
                </div>

                <div class="history-main">
                    ${state.searchQuery && state.searchResults.length > 0 ? `
                        <div class="search-results">
                            <h3 class="results-title">Search Results</h3>
                            ${searchResultsList}
                        </div>
                    ` : state.selectedMeeting ? `
                        <div class="meeting-detail">
                            <div class="meeting-detail-header">
                                <div class="meeting-detail-title-row">
                                    <h2>${escapeHtml(state.selectedMeeting.title || 'Meeting Details')}</h2>
                                    <button class="btn btn-ghost btn-sm btn-danger" onclick="deleteMeeting(${state.selectedMeeting.id})" title="Delete meeting">
                                        <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                                        </svg>
                                        Delete
                                    </button>
                                </div>
                                <span class="detail-project">${escapeHtml(state.selectedMeeting.project_key)}</span>
                            </div>
                            ${state.selectedMeeting.tickets_created?.length ? `
                                <div class="detail-tickets">
                                    <strong>Tickets Created:</strong>
                                    ${state.selectedMeeting.tickets_created.map(t => `
                                        <a href="${state.jiraConfig?.jira_base_url}/browse/${t}" target="_blank" class="ticket-link">${escapeHtml(t)}</a>
                                    `).join(', ')}
                                </div>
                            ` : ''}
                            ${state.selectedMeeting.summary ? `
                                <div class="detail-section">
                                    <h4>Summary</h4>
                                    <div class="detail-summary">${formatContent(state.selectedMeeting.summary)}</div>
                                </div>
                            ` : ''}
                            <div class="detail-section">
                                <h4>Transcription</h4>
                                <div class="detail-transcription">${escapeHtml(state.selectedMeeting.transcription)}</div>
                            </div>
                        </div>
                    ` : `
                        <div class="empty-detail">
                            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                            </svg>
                            <p>Select a meeting or search to view details</p>
                        </div>
                    `}
                </div>
            </div>
        </main>
    `;
}

function handleSearchKeyup(event) {
    state.searchQuery = event.target.value;
    if (event.key === 'Enter') {
        searchMeetings(state.searchQuery);
    }
}

function renderKanban() {
    if (state.workTicketsLoading) {
        return '<div class="loading">Loading tickets...</div>';
    }

    if (state.workStatuses.length === 0) {
        return '<div class="empty-state">No workflow statuses found. Configure a project first.</div>';
    }

    // Group tickets by status
    const ticketsByStatus = {};
    state.workStatuses.forEach(s => ticketsByStatus[s.id] = []);
    state.workTickets.forEach(t => {
        if (ticketsByStatus[t.statusId]) {
            ticketsByStatus[t.statusId].push(t);
        }
    });

    const columns = state.workStatuses.map(status => `
        <div class="kanban-column" data-status="${status.id}">
            <div class="kanban-column-header">
                <span class="status-name">${status.name}</span>
                <span class="status-count">${ticketsByStatus[status.id].length}</span>
            </div>
            <div class="kanban-cards">
                ${ticketsByStatus[status.id].map(ticket => `
                    <div class="kanban-card" onclick="loadTicketDetails('${ticket.key}')">
                        <div class="ticket-key">${ticket.key}</div>
                        <div class="ticket-summary">${escapeHtml(ticket.summary)}</div>
                        <div class="ticket-meta">
                            ${ticket.priorityIcon ? `<img src="${ticket.priorityIcon}" class="priority-icon" alt="${ticket.priority}">` : ''}
                            ${ticket.issueTypeIcon ? `<img src="${ticket.issueTypeIcon}" class="type-icon" alt="${ticket.issueType}">` : ''}
                            ${ticket.assigneeAvatar ? `<img src="${ticket.assigneeAvatar}" class="assignee-avatar" alt="${ticket.assignee}">` : ''}
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `).join('');

    return `<div class="kanban-board">${columns}</div>`;
}

function renderTicketDetail() {
    if (state.selectedTicketLoading) {
        return '<div class="loading">Loading ticket...</div>';
    }

    const ticket = state.selectedTicket;
    if (!ticket) {
        return '<div class="error">Ticket not found</div>';
    }

    const project = state.projects.find(p => p.project_key === state.selectedProject);

    return `
        <div class="ticket-detail-panel">
            <div class="ticket-detail-header">
                <button class="back-btn" onclick="state.workMode = 'kanban'; state.selectedTicket = null; render();">
                    ← Back to Board
                </button>
                <div class="ticket-key-large">${ticket.key}</div>
            </div>

            <h2 class="ticket-title">${escapeHtml(ticket.summary)}</h2>

            <div class="ticket-metadata">
                <div class="meta-item"><strong>Status:</strong> ${ticket.status}</div>
                <div class="meta-item"><strong>Priority:</strong> ${ticket.priority || 'None'}</div>
                <div class="meta-item"><strong>Type:</strong> ${ticket.issueType}</div>
                <div class="meta-item"><strong>Assignee:</strong> ${ticket.assignee || 'Unassigned'}</div>
            </div>

            <div class="ticket-description">
                <h3>Description</h3>
                <div class="description-content">
                    ${ticket.descriptionHtml ? sanitizeHtml(ticket.descriptionHtml) : '<em>No description</em>'}
                </div>
            </div>

            <div class="ticket-comments">
                <h3>Comments (${ticket.comments.length})</h3>
                ${ticket.comments.length === 0 ? '<em>No comments</em>' : ticket.comments.map(c => `
                    <div class="comment">
                        <div class="comment-header">
                            ${c.authorAvatar ? `<img src="${c.authorAvatar}" class="comment-avatar">` : ''}
                            <strong>${escapeHtml(c.author)}</strong>
                            <span class="comment-date">${new Date(c.created).toLocaleDateString()}</span>
                        </div>
                        <div class="comment-body">${typeof c.body === 'string' ? escapeHtml(c.body) : '<em>Rich content</em>'}</div>
                    </div>
                `).join('')}
            </div>

            <div class="ticket-actions">
                <button class="btn-primary btn-large" onclick="startWork(${project?.id}, '${ticket.key}')" ${!project?.gitlab_projects ? 'disabled title="Configure GitLab repos first"' : ''}>
                    Start Work
                </button>
            </div>
        </div>
    `;
}

function renderProcessingConsole() {
    return `
        <div class="processing-console">
            <div class="status-bar">
                <div class="status-indicator">
                    <div class="status-dot active"></div>
                    <span class="status-text">Starting work...</span>
                </div>
                <div class="status-actions">
                    <button class="btn btn-danger btn-sm" onclick="handleAbort()">
                        <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                        Stop
                    </button>
                </div>
            </div>
            <div class="live-console">
                <div class="console-header">
                    <div class="console-dots">
                        <div class="console-dot red"></div>
                        <div class="console-dot yellow"></div>
                        <div class="console-dot green"></div>
                    </div>
                    <span class="console-title">work output</span>
                </div>
                <div class="console-body" id="console-output">
                    <div class="console-line">
                        <span class="console-prompt">></span>
                        <span class="console-text thinking">Preparing workspace...</span>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderDashboard() {
    return `
        <div class="app-layout">
            ${renderHeader()}
            ${renderOutputStage()}
        </div>
    `;
}

// =====================================================
// Event Handlers
// =====================================================

function selectProject(key) {
    state.selectedProject = key;
    render();
}

function setMode(mode) {
    state.mode = mode;
    state.lastResult = null;
    if (mode === 'work' && state.selectedProject) {
        state.workMode = 'kanban';
        loadWorkflowStatuses(state.selectedProject);
        loadKanbanTickets(state.selectedProject);
    }
    render();
}

function clearResult() {
    state.lastResult = null;
    state.sessionId = null;  // Clear session for fresh start
    state.conversationMessages = [];  // Clear conversation history
    render();
}

async function handleSubmit() {
    const input = document.getElementById('input-text')?.value.trim();
    if (!input || !state.selectedProject) return;

    try {
        if (state.mode === 'meeting') {
            await processMeeting(input, state.selectedProject);
        } else {
            await askQuestion(input, state.selectedProject, false);  // false = new question
        }
    } catch (e) {
        state.isProcessing = false;
        render();
        showToast(e.message, 'error');
    }
}

async function handleAbort() {
    await abortProcessing();
}

async function handleRemoveProject(projectId) {
    try {
        await removeProject(projectId);
        render();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

async function handleUpdateProjectField(projectId, field, value) {
    console.log(`[DEBUG] Updating project ${projectId}, field: ${field}, value:`, JSON.stringify(value));
    try {
        // Send empty string as empty string (not null) so backend can clear the field
        const result = await updateProject(projectId, { [field]: value });
        console.log(`[DEBUG] Update result:`, result);
        showToast('Project settings updated', 'success');
        render(); // Re-render to reflect changes
    } catch (e) {
        console.error(`[DEBUG] Update error:`, e);
        showToast(e.message, 'error');
    }
}

// =====================================================
// Utilities
// =====================================================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function truncate(text, len) {
    if (!text || text.length <= len) return text;
    return text.substring(0, len) + '...';
}

function sanitizeHtml(html) {
    if (!html) return '';
    // Use DOMPurify if available, otherwise fall back to basic script tag stripping
    if (typeof DOMPurify !== 'undefined') {
        return DOMPurify.sanitize(html, {
            ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'b', 'i', 'u', 'a', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'code', 'pre', 'span', 'div', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'img', 'hr'],
            ALLOWED_ATTR: ['href', 'target', 'rel', 'src', 'alt', 'class', 'style', 'title', 'width', 'height'],
            ALLOW_DATA_ATTR: false
        });
    }
    // Fallback: strip script tags and event handlers
    return html
        .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
        .replace(/on\w+\s*=\s*(['"]).*?\1/gi, '')
        .replace(/on\w+\s*=\s*[^\s>]+/gi, '');
}

function formatContent(content) {
    if (!content) return '';
    // Use marked.js for proper markdown rendering
    let html = marked.parse(content);
    // Sanitize the HTML to prevent XSS from markdown content
    html = sanitizeHtml(html);
    // Highlight Jira ticket references
    html = html.replace(/([A-Z]+-\d+)/g, '<span class="ticket-ref">$1</span>');
    return html;
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = escapeHtml(message);
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// =====================================================
// Main Render
// =====================================================

function render() {
    const path = getCurrentPath();
    const app = document.getElementById('app');

    if (!state.token && !['/login', '/register'].includes(path)) {
        navigate('/login');
        return;
    }
    if (state.token && ['/login', '/register'].includes(path)) {
        navigate('/');
        return;
    }

    // Redirect from history if feature not enabled
    const hasEmbeddings = state.projects.some(p => p.embeddings_enabled);
    if (path === '/history' && !hasEmbeddings) {
        navigate('/');
        return;
    }

    let html;
    switch (path) {
        case '/login': html = renderLoginPage(); break;
        case '/register': html = renderRegisterPage(); break;
        case '/settings': html = renderSettings(); break;
        case '/history':
            html = renderHistory();
            // Auto-load meetings if not already loaded
            if (state.meetings.length === 0 && !state.meetingsLoading) {
                loadMeetings();
            }
            break;
        default: html = renderDashboard();
    }

    app.innerHTML = html;
    attachEventListeners();
}

function attachEventListeners() {
    document.getElementById('login-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const errorEl = document.getElementById('login-error');
        try {
            await login(document.getElementById('email').value, document.getElementById('password').value);
            navigate('/');
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.classList.remove('hidden');
        }
    });

    document.getElementById('register-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const errorEl = document.getElementById('register-error');
        try {
            await register(document.getElementById('email').value, document.getElementById('password').value, document.getElementById('fullName').value);
            await login(document.getElementById('email').value, document.getElementById('password').value);
            navigate('/');
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.classList.remove('hidden');
        }
    });

    document.getElementById('jira-config-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const messageEl = document.getElementById('config-message');
        const config = {
            jira_base_url: document.getElementById('jiraUrl').value,
            jira_email: document.getElementById('jiraEmail').value
        };
        const token = document.getElementById('jiraToken').value;
        if (token) config.jira_api_token = token;

        try {
            await saveJiraConfig(config);
            messageEl.className = 'alert alert-success';
            messageEl.textContent = 'Saved successfully';
            messageEl.classList.remove('hidden');
        } catch (err) {
            messageEl.className = 'alert alert-error';
            messageEl.textContent = err.message;
            messageEl.classList.remove('hidden');
        }
    });

    document.getElementById('gitlab-config-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const messageEl = document.getElementById('gitlab-message');
        const config = {};
        const gitlabUrl = document.getElementById('gitlabUrl').value;
        const gitlabToken = document.getElementById('gitlabToken').value;

        if (gitlabUrl) config.gitlab_url = gitlabUrl;
        if (gitlabToken) config.gitlab_token = gitlabToken;

        // Allow clearing GitLab config
        if (!gitlabUrl && !gitlabToken) {
            config.gitlab_url = '';
            config.gitlab_token = '';
        }

        try {
            await saveJiraConfig(config);
            messageEl.className = 'alert alert-success';
            messageEl.textContent = 'GitLab settings saved';
            messageEl.classList.remove('hidden');
            render();  // Re-render to show/hide GitLab project fields
        } catch (err) {
            messageEl.className = 'alert alert-error';
            messageEl.textContent = err.message;
            messageEl.classList.remove('hidden');
        }
    });

    document.getElementById('add-project-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        try {
            await addProject(document.getElementById('projectKey').value.toUpperCase(), null, state.projects.length === 0);
            render();
        } catch (err) {
            showToast(err.message, 'error');
        }
    });
}

window.addEventListener('popstate', render);

(async () => {
    if (state.token) await loadUserData();
    render();
})();
