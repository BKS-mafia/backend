// Базовые URL будут браться из селектора
let API_BASE_URL = 'http://localhost:8000';
let WS_BASE_URL = 'ws://localhost:8000';

// Состояние приложения
let currentRoomId = null;
let currentSessionToken = null;
let currentHostToken = null;
let ws = null;

// DOM Элементы
const els = {
    // Индикаторы
    wsStatusIndicator: document.getElementById('ws-status-indicator'),
    wsStatusText: document.getElementById('ws-status-text'),
    
    // Селектор сервера
    selectServer: document.getElementById('select-server'),
    
    // Инпуты
    inputRoomId: document.getElementById('input-room-id'),
    inputNickname: document.getElementById('input-nickname'),
    inputSessionToken: document.getElementById('input-session-token'),
    inputChatMsg: document.getElementById('input-chat-msg'),
    inputTargetId: document.getElementById('input-target-id'),
    selectNightAction: document.getElementById('select-night-action'),
    
    // Настройки комнаты
    inputTotalPlayers: document.getElementById('input-total-players'),
    inputAiCount: document.getElementById('input-ai-count'),
    checkboxAllAI: document.getElementById('checkbox-all-ai'),
    checkboxShowAIMessages: document.getElementById('checkbox-show-ai-messages'),
    
    // Кнопки
    btnGetRooms: document.getElementById('btn-get-rooms'),
    btnCreateRoom: document.getElementById('btn-create-room'),
    btnGetRoom: document.getElementById('btn-get-room'),
    btnJoinRoom: document.getElementById('btn-join-room'),
    btnGetPlayers: document.getElementById('btn-get-players'),
    
    btnWsConnect: document.getElementById('btn-ws-connect'),
    btnWsDisconnect: document.getElementById('btn-ws-disconnect'),
    btnWsReady: document.getElementById('btn-ws-ready'),
    btnWsStart: document.getElementById('btn-ws-start'),
    btnWsChat: document.getElementById('btn-ws-chat'),
    btnWsVote: document.getElementById('btn-ws-vote'),
    btnWsNightAction: document.getElementById('btn-ws-night-action'),
    btnClearLogs: document.getElementById('btn-clear-logs'),
    btnCreateAllAIRoom: document.getElementById('btn-create-all-ai-room'),
    
    // Контейнеры
    logsContainer: document.getElementById('logs-container')
};

// --- Логирование ---
// Флаг для отображения сообщений от ИИ
let showAIMessages = true;

function log(message, type = 'info', data = null, isAIMessage = false) {
    const entry = document.createElement('div');
    
    // Класс для сообщений от ИИ
    let entryClass = `log-entry log-${type}`;
    if (isAIMessage) {
        entryClass += ' log-ai-message';
    }
    entry.className = entryClass;
    
    const time = new Date().toLocaleTimeString();
    const timeSpan = `<span class="log-time">[${time}]</span>`;
    
    let typeLabel = 'INFO';
    if (type === 'success') typeLabel = 'SUCCESS';
    if (type === 'error') typeLabel = 'ERROR';
    if (type === 'ws-send') typeLabel = 'WS_SEND';
    if (type === 'ws-recv') typeLabel = 'WS_RECV';
    if (isAIMessage) typeLabel = 'AI_MSG';
    
    const typeSpan = `<span class="log-type">${typeLabel}</span>`;
    
    let dataStr = '';
    if (data) {
        try {
            dataStr = typeof data === 'object' ? JSON.stringify(data, null, 2) : data;
            dataStr = `\n${dataStr}`;
        } catch (e) {
            dataStr = `\n[Unserializable data]`;
        }
    }
    
    entry.innerHTML = `${timeSpan}${typeSpan}${message}${dataStr}`;
    els.logsContainer.appendChild(entry);
    els.logsContainer.scrollTop = els.logsContainer.scrollHeight;
}

els.btnClearLogs.addEventListener('click', () => {
    els.logsContainer.innerHTML = '';
});

// --- Обновление URL сервера ---
function updateServerUrls() {
    API_BASE_URL = els.selectServer.value;
    WS_BASE_URL = API_BASE_URL.replace('http://', 'ws://').replace('https://', 'wss://');
    log(`Сервер изменен на: ${API_BASE_URL}`, 'info');
}

els.selectServer.addEventListener('change', updateServerUrls);
// Инициализация при загрузке
updateServerUrls();

// --- HTTP Запросы ---
async function apiRequest(endpoint, method = 'GET', body = null, headers = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json',
            ...headers
        }
    };
    
    if (body) {
        options.body = JSON.stringify(body);
    }
    
    log(`HTTP ${method} ${endpoint}`, 'info', body);
    
    try {
        const response = await fetch(url, options);
        const isJson = response.headers.get('content-type')?.includes('application/json');
        const data = isJson ? await response.json() : await response.text();
        
        if (!response.ok) {
            log(`HTTP Error ${response.status}`, 'error', data);
            throw new Error(`HTTP ${response.status}`);
        }
        
        log(`HTTP Success ${response.status}`, 'success', data);
        return data;
    } catch (error) {
        log(`Fetch Error: ${error.message}`, 'error');
        throw error;
    }
}

// --- Обработчики кнопок HTTP ---

els.btnGetRooms.addEventListener('click', async () => {
    await apiRequest('/api/rooms/');
});

// Обработчик чекбокса "Все игроки ИИ"
els.checkboxAllAI.addEventListener('change', () => {
    if (els.checkboxAllAI.checked) {
        const totalPlayers = parseInt(els.inputTotalPlayers.value, 10) || 8;
        els.inputAiCount.value = totalPlayers;
        els.inputAiCount.disabled = true;
    } else {
        els.inputAiCount.disabled = false;
    }
});

// Обновление aiCount при изменении totalPlayers
els.inputTotalPlayers.addEventListener('change', () => {
    if (els.checkboxAllAI.checked) {
        const totalPlayers = parseInt(els.inputTotalPlayers.value, 10) || 8;
        els.inputAiCount.value = totalPlayers;
    }
});

// Обработчик чекбокса "Показывать сообщения нейросетей"
els.checkboxShowAIMessages.addEventListener('change', () => {
    showAIMessages = els.checkboxShowAIMessages.checked;
    log(`Режим показа сообщений ИИ: ${showAIMessages ? 'ВКЛ' : 'ВЫКЛ'}`, 'info');
});

els.btnCreateRoom.addEventListener('click', async () => {
    try {
        // Генерируем случайный UUID для комнаты
        const roomId = crypto.randomUUID();
        const hostToken = crypto.randomUUID();
        
        const totalPlayers = parseInt(els.inputTotalPlayers.value, 10) || 8;
        const aiCount = parseInt(els.inputAiCount.value, 10) || 0;
        const peopleCount = totalPlayers - aiCount;
        const showAIMessages = els.checkboxShowAIMessages.checked;
        
        const payload = {
            room_id: roomId,
            host_token: hostToken,
            status: "lobby",
            totalPlayers: totalPlayers,
            aiCount: aiCount,
            peopleCount: peopleCount,
            settings: {
                showAIMessages: showAIMessages
            }
        };
        
        const data = await apiRequest('/api/rooms/', 'POST', payload);
        
        currentRoomId = data.room_id;
        currentHostToken = data.host_token;
        els.inputRoomId.value = currentRoomId;
        
        log(`Комната создана. Room ID: ${currentRoomId}`, 'success');
        log(`Настройки: игроков=${totalPlayers}, AI=${aiCount}, показ сообщений ИИ=${showAIMessages ? 'ВКЛ' : 'ВЫКЛ'}`, 'info');
    } catch (e) {
        // Ошибка уже залогирована в apiRequest
    }
});

// Кнопка "Все ИИ" - создать комнату где все игроки ИИ и сразу запустить игру
els.btnCreateAllAIRoom.addEventListener('click', async () => {
    try {
        const roomId = crypto.randomUUID();
        const hostToken = crypto.randomUUID();
        const totalPlayers = parseInt(els.inputTotalPlayers.value, 10) || 8;
        const showAIMessages = els.checkboxShowAIMessages.checked;
        
        const payload = {
            room_id: roomId,
            host_token: hostToken,
            status: "lobby",
            totalPlayers: totalPlayers,
            aiCount: totalPlayers,  // Все игроки ИИ
            peopleCount: 0,
            settings: {
                showAIMessages: showAIMessages
            }
        };
        
        const data = await apiRequest('/api/rooms/', 'POST', payload);
        
        currentRoomId = data.room_id;
        currentHostToken = data.host_token;
        els.inputRoomId.value = currentRoomId;
        
        log(`Комната "Все ИИ" создана. Room ID: ${currentRoomId}`, 'success');
        log(`Запуск игры с ${totalPlayers} ИИ-игроками...`, 'info');
        
        // Автоматически присоединяемся как хост (без реального игрока, просто для получения events)
        // Создаём фиктивного игрока для WebSocket подключения
        const playerId = crypto.randomUUID();
        const joinPayload = {
            player_id: playerId,
            room_id: 0,
            nickname: "Host_Observer",
            is_ai: false
        };
        
        const joinData = await apiRequest(`/api/rooms/${currentRoomId}/join`, 'POST', joinPayload);
        currentSessionToken = joinData.session_token;
        els.inputSessionToken.value = currentSessionToken;
        
        log(`Присоединён к комнате. Подключаемся к WebSocket...`, 'info');
        
        // Подключаемся к WebSocket для получения событий
        await connectToWebSocket();
        
        // Используем HTTP API для старта игры
        setTimeout(async () => {
            log(`Запускаем игру через HTTP API...`, 'info');
            try {
                const startData = await apiRequest(`/api/rooms/${currentRoomId}/game/start`, 'POST', {});
                log(`Игра запущена! ID игры: ${startData.game_id}`, 'success');
                log(`Ожидаем сообщений от нейросетей...`, 'info');
            } catch (e) {
                log(`Ошибка запуска игры: ${e.message}`, 'error');
            }
        }, 1000);
        
    } catch (e) {
        // Ошибка уже залогирована в apiRequest
    }
});

// Функция подключения к WebSocket (извлечена для переиспользования)
function connectToWebSocket() {
    return new Promise((resolve, reject) => {
        const roomId = els.inputRoomId.value.trim();
        const token = els.inputSessionToken.value.trim();
        
        if (!roomId || !token) {
            log('Для подключения нужны Room ID и Session Token', 'error');
            reject(new Error('No room or token'));
            return;
        }
        
        if (ws) {
            ws.close();
        }
        
        els.wsStatusIndicator.className = 'status-indicator connecting';
        els.wsStatusText.textContent = 'Connecting...';
        
        const wsUrl = `${WS_BASE_URL}/ws/rooms/${roomId}?token=${token}`;
        log(`Подключение к WS: ${wsUrl}`, 'info');
        
        ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            log('WebSocket соединение установлено', 'success');
            updateWsUI(true);
            resolve();
        };
        
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                // Проверяем, является ли сообщение от ИИ
                let isAIMessage = false;
                
                if (data.is_ai === true || data.from_ai === true) {
                    isAIMessage = true;
                } else if (data.data && (data.data.is_ai === true || data.data.from_ai === true)) {
                    isAIMessage = true;
                } else if (data.player && data.player.is_ai === true) {
                    isAIMessage = true;
                }
                
                // Проверяем тип сообщения - чат от ИИ
                const isAIChat = (data.event === 'chat_message' || data.type === 'chat_message') && isAIMessage;
                
                // Если это сообщение от ИИ и режим показа выключен - не показываем
                if ((isAIMessage || isAIChat) && !showAIMessages) {
                    return; // Пропускаем сообщение от ИИ
                }
                
                log(`Получено WS: ${data.type || data.event || 'unknown'}`, 'ws-recv', data, isAIMessage || isAIChat);
            } catch (e) {
                log(`Получено WS (raw): ${event.data}`, 'ws-recv');
            }
        };
        
        ws.onclose = (event) => {
            log(`WebSocket отключен. Код: ${event.code}, Причина: ${event.reason}`, 'warning');
            updateWsUI(false);
            ws = null;
        };
        
        ws.onerror = (error) => {
            log('WebSocket ошибка', 'error');
            updateWsUI(false);
            reject(error);
        };
    });
}

els.btnGetRoom.addEventListener('click', async () => {
    const roomId = els.inputRoomId.value.trim();
    if (!roomId) return log('Введите Room ID', 'error');
    await apiRequest(`/api/rooms/${roomId}`);
});

els.btnJoinRoom.addEventListener('click', async () => {
    const roomId = els.inputRoomId.value.trim();
    const nickname = els.inputNickname.value.trim();
    
    if (!roomId) return log('Введите Room ID', 'error');
    if (!nickname) return log('Введите Никнейм', 'error');
    
    try {
        const playerId = crypto.randomUUID();
        const payload = {
            player_id: playerId,
            room_id: 0, // Бэкенд игнорирует это поле при join, берет из URL
            nickname: nickname,
            is_ai: false
        };
        
        const data = await apiRequest(`/api/rooms/${roomId}/join`, 'POST', payload);
        
        currentSessionToken = data.session_token;
        els.inputSessionToken.value = currentSessionToken;
        currentRoomId = roomId;
        
        log(`Успешно присоединились. Session Token получен.`, 'success');
    } catch (e) {
        // Ошибка уже залогирована
    }
});

els.btnGetPlayers.addEventListener('click', async () => {
    const roomId = els.inputRoomId.value.trim();
    if (!roomId) return log('Введите Room ID', 'error');
    await apiRequest(`/api/rooms/${roomId}/players`);
});

// --- WebSocket Логика ---

function updateWsUI(connected) {
    els.wsStatusIndicator.className = `status-indicator ${connected ? 'connected' : 'disconnected'}`;
    els.wsStatusText.textContent = connected ? 'WS Connected' : 'WS Disconnected';
    
    els.btnWsConnect.disabled = connected;
    els.btnWsDisconnect.disabled = !connected;
    
    els.btnWsReady.disabled = !connected;
    els.btnWsStart.disabled = !connected;
    els.btnWsChat.disabled = !connected;
    els.btnWsVote.disabled = !connected;
    els.btnWsNightAction.disabled = !connected;
}

function wsSend(type, payload = {}) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        return log('WebSocket не подключен', 'error');
    }
    
    const message = { type, ...payload };
    ws.send(JSON.stringify(message));
    log(`Отправлено WS: ${type}`, 'ws-send', message);
}

els.btnWsConnect.addEventListener('click', () => {
    connectToWebSocket().catch(() => {});
});

els.btnWsDisconnect.addEventListener('click', () => {
    if (ws) {
        ws.close();
    }
});

// --- Игровые действия WS ---

els.btnWsReady.addEventListener('click', () => {
    wsSend('ready');
});

els.btnWsStart.addEventListener('click', () => {
    wsSend('start_game');
});

els.btnWsChat.addEventListener('click', () => {
    const content = els.inputChatMsg.value.trim();
    if (!content) return log('Введите сообщение', 'error');
    
    wsSend('chat_message', { content });
    els.inputChatMsg.value = '';
});

els.btnWsVote.addEventListener('click', () => {
    const targetId = parseInt(els.inputTargetId.value.trim(), 10);
    if (isNaN(targetId)) return log('Введите корректный Target ID', 'error');
    
    wsSend('vote_action', { target_player_id: targetId });
});

els.btnWsNightAction.addEventListener('click', () => {
    const targetId = parseInt(els.inputTargetId.value.trim(), 10);
    const actionType = els.selectNightAction.value;
    
    if (isNaN(targetId)) return log('Введите корректный Target ID', 'error');
    
    wsSend('night_action', { 
        action_type: actionType,
        target_player_id: targetId 
    });
});

// Поддержка Enter в поле чата
els.inputChatMsg.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !els.btnWsChat.disabled) {
        els.btnWsChat.click();
    }
});