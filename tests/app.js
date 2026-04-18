// AI Mafia - Тестовый интерфейс JavaScript

// Базовые URL
let API_BASE_URL = 'http://localhost:8000';
let WS_BASE_URL = 'ws://localhost:8000';

// Состояние приложения
let currentRoomId = null;
let currentSessionToken = null;
let currentHostToken = null;
let currentPlayerId = null;
let currentRole = null;
let isAlive = true;
let currentPhase = 'lobby';
let currentDay = 0;
let ws = null;
let reconnectAttempts = 0;
let maxReconnectAttempts = 5;
let showAIMessages = true;

// Текущий активный чат
let activeChat = 'cityGroup';

// Список игроков
let players = [];
let myPlayerId = null;

// DOM Элементы
const els = {
    // Индикаторы
    wsStatusIndicator: document.getElementById('ws-status-indicator'),
    wsStatusText: document.getElementById('ws-status-text'),
    
    // Селектор сервера
    selectServer: document.getElementById('select-server'),
    
    // Инпуты комнаты
    inputRoomId: document.getElementById('input-room-id'),
    inputNickname: document.getElementById('input-nickname'),
    inputSessionToken: document.getElementById('input-session-token'),
    inputTotalPlayers: document.getElementById('input-total-players'),
    inputAiCount: document.getElementById('input-ai-count'),
    checkboxAllAI: document.getElementById('checkbox-all-ai'),
    checkboxShowAIMessages: document.getElementById('checkbox-show-ai-messages'),
    checkboxIsAI: document.getElementById('checkbox-is-ai'),
    
    // Отображение комнаты
    displayRoomId: document.getElementById('display-room-id'),
    displayShortId: document.getElementById('display-short-id'),
    displayHostToken: document.getElementById('display-host-token'),
    roomInfo: document.getElementById('room-info'),
    
    // Информация о игре
    displayPhase: document.getElementById('display-phase'),
    displayDay: document.getElementById('display-day'),
    displayRole: document.getElementById('display-role'),
    displayStatus: document.getElementById('display-status'),
    
    // Чат
    chatMessages: document.getElementById('chat-messages'),
    inputChatMsg: document.getElementById('input-chat-msg'),
    tabCityGroup: document.getElementById('tab-cityGroup'),
    tabMafiaGroup: document.getElementById('tab-mafiaGroup'),
    tabRoleChat: document.getElementById('tab-roleChat'),
    
    // Игроки
    playersList: document.getElementById('players-list'),
    
    // Действия
    nightActions: document.getElementById('night-actions'),
    votingActions: document.getElementById('voting-actions'),
    selectNightAction: document.getElementById('select-night-action'),
    selectNightTarget: document.getElementById('select-night-target'),
    selectVoteTarget: document.getElementById('select-vote-target'),
    
    // Секции
    turingTestSection: document.getElementById('turing-test-section'),
    votingResults: document.getElementById('voting-results'),
    winnerSection: document.getElementById('winner-section'),
    winnerTeam: document.getElementById('winner-team'),
    
    // Кнопки
    btnCreateRoom: document.getElementById('btn-create-room'),
    btnCreateAllAI: document.getElementById('btn-create-all-ai'),
    btnJoinRoom: document.getElementById('btn-join-room'),
    btnWsConnect: document.getElementById('btn-ws-connect'),
    btnWsDisconnect: document.getElementById('btn-ws-disconnect'),
    btnWsReady: document.getElementById('btn-ws-ready'),
    btnWsStart: document.getElementById('btn-ws-start'),
    btnWsChat: document.getElementById('btn-ws-chat'),
    btnWsVote: document.getElementById('btn-ws-vote'),
    btnWsNightAction: document.getElementById('btn-ws-night-action'),
    btnRefreshPlayers: document.getElementById('btn-refresh-players'),
    btnClearLogs: document.getElementById('btn-clear-logs'),
    btnSubmitTuring: document.getElementById('btn-submit-turing'),
    
    // Логи
    logsContainer: document.getElementById('logs-container')
};

// ==================== ЛОГИРОВАНИЕ ====================

function log(message, type = 'info', data = null, isAIMessage = false) {
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    
    const time = new Date().toLocaleTimeString();
    const timeSpan = `<span class="log-time">${time}</span>`;
    
    let typeLabel = 'INFO';
    if (type === 'success') typeLabel = 'SUCCESS';
    if (type === 'error') typeLabel = 'ERROR';
    if (type === 'warning') typeLabel = 'WARN';
    if (type === 'ws-send') typeLabel = 'WS_SEND';
    if (type === 'ws-recv') typeLabel = 'WS_RECV';
    if (isAIMessage) typeLabel = 'AI_MSG';
    
    const typeSpan = `<span class="log-type ${type}">${typeLabel}</span>`;
    
    let dataStr = '';
    if (data) {
        try {
            dataStr = typeof data === 'object' ? JSON.stringify(data, null, 2) : data;
            dataStr = `<div class="log-data">${dataStr}</div>`;
        } catch (e) {
            dataStr = '<div class="log-data">[Unserializable data]</div>';
        }
    }
    
    entry.innerHTML = `${timeSpan}${typeSpan}<span class="log-content">${message}</span>${dataStr}`;
    els.logsContainer.appendChild(entry);
    els.logsContainer.scrollTop = els.logsContainer.scrollHeight;
}

els.btnClearLogs.addEventListener('click', () => {
    els.logsContainer.innerHTML = '';
});

// ==================== HTTP ЗАПРОСЫ ====================

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

// ==================== ОБНОВЛЕНИЕ URL СЕРВЕРА ====================

function updateServerUrls() {
    API_BASE_URL = els.selectServer.value;
    WS_BASE_URL = API_BASE_URL.replace('http://', 'ws://').replace('https://', 'wss://');
    log(`Сервер изменен на: ${API_BASE_URL}`, 'info');
}

els.selectServer.addEventListener('change', updateServerUrls);
updateServerUrls();

// ==================== СОЗДАНИЕ КОМНАТЫ ====================

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
        const roomId = crypto.randomUUID();
        const hostToken = crypto.randomUUID();
        
        const totalPlayers = parseInt(els.inputTotalPlayers.value, 10) || 8;
        const aiCount = parseInt(els.inputAiCount.value, 10) || 0;
        const peopleCount = totalPlayers - aiCount;
        
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
        
        currentRoomId = data.roomId;
        currentHostToken = data.hostToken;
        
        // Обновляем UI
        els.inputRoomId.value = currentRoomId;
        els.displayRoomId.textContent = currentRoomId.substring(0, 8) + '...';
        els.displayShortId.textContent = data.shortId || '-';
        els.displayHostToken.textContent = currentHostToken.substring(0, 8) + '...';
        els.roomInfo.classList.add('visible');
        
        log(`Комната создана. Room ID: ${currentRoomId}`, 'success');
        log(`Настройки: игроков=${totalPlayers}, AI=${aiCount}`, 'info');
        
        // Включаем кнопку старта для хоста
        els.btnWsStart.disabled = false;
        
    } catch (e) {
        // Ошибка уже залогирована
    }
});

// Кнопка "Все ИИ"
els.btnCreateAllAI.addEventListener('click', async () => {
    try {
        const roomId = crypto.randomUUID();
        const hostToken = crypto.randomUUID();
        const totalPlayers = parseInt(els.inputTotalPlayers.value, 10) || 8;
        
        const payload = {
            room_id: roomId,
            host_token: hostToken,
            status: "lobby",
            totalPlayers: totalPlayers,
            aiCount: totalPlayers,
            peopleCount: 0,
            settings: {
                showAIMessages: showAIMessages
            }
        };
        
        const data = await apiRequest('/api/rooms/', 'POST', payload);
        
        currentRoomId = data.roomId;
        currentHostToken = data.hostToken;
        
        els.inputRoomId.value = currentRoomId;
        els.displayRoomId.textContent = currentRoomId.substring(0, 8) + '...';
        els.displayShortId.textContent = data.shortId || '-';
        els.displayHostToken.textContent = currentHostToken.substring(0, 8) + '...';
        els.roomInfo.classList.add('visible');
        
        log(`Комната "Все ИИ" создана. Room ID: ${currentRoomId}`, 'success');
        
        // Присоединяемся как наблюдатель
        const playerId = crypto.randomUUID();
        const joinPayload = {
            player_id: playerId,
            room_id: 0,
            nickname: "Host_Observer",
            is_ai: false
        };
        
        const joinData = await apiRequest(`/api/rooms/${currentRoomId}/join`, 'POST', joinPayload);
        currentSessionToken = joinData.sessionToken;
        els.inputSessionToken.value = currentSessionToken;
        
        log(`Присоединён к комнате. Подключаемся к WebSocket...`, 'info');
        
        // Подключаемся к WebSocket
        await connectToWebSocket();
        
        // Запускаем игру
        setTimeout(async () => {
            try {
                const startData = await apiRequest(`/api/rooms/${currentRoomId}/game/start`, 'POST', {});
                log(`Игра запущена! ID игры: ${startData.game_id}`, 'success');
            } catch (e) {
                log(`Ошибка запуска игры: ${e.message}`, 'error');
            }
        }, 1000);
        
    } catch (e) {
        // Ошибка уже залогирована
    }
});

// ==================== ПРИСОЕДИНЕНИЕ К КОМНАТЕ ====================

els.btnJoinRoom.addEventListener('click', async () => {
    const roomId = els.inputRoomId.value.trim();
    const nickname = els.inputNickname.value.trim();
    const isAI = els.checkboxIsAI.checked;
    
    if (!roomId) return log('Введите Room ID', 'error');
    if (!nickname) return log('Введите Никнейм', 'error');
    
    try {
        const playerId = crypto.randomUUID();
        currentPlayerId = playerId;
        
        const payload = {
            player_id: playerId,
            room_id: 0,
            nickname: nickname,
            is_ai: isAI
        };
        
        const data = await apiRequest(`/api/rooms/${roomId}/join`, 'POST', payload);
        
        currentSessionToken = data.sessionToken;
        currentRoomId = roomId;
        els.inputSessionToken.value = currentSessionToken;
        
        log(`Успешно присоединились как ${nickname}`, 'success');
        
        // Включаем кнопки
        els.btnWsConnect.disabled = false;
        
    } catch (e) {
        // Ошибка уже залогирована
    }
});

// ==================== ОБНОВЛЕНИЕ СПИСКА ИГРОКОВ ====================

function updatePlayersList() {
    if (players.length === 0) {
        els.playersList.innerHTML = '<div style="text-align: center; color: #6b7280; padding: 20px;">Нет игроков в комнате</div>';
        return;
    }
    
    els.playersList.innerHTML = players.map(player => {
        const isSelf = player.player_id === myPlayerId;
        const avatarClass = player.is_ai ? 'ai' : 'human';
        const initial = player.nickname ? player.nickname.charAt(0).toUpperCase() : '?';
        const statusClass = player.is_alive !== false ? 'alive' : 'dead';
        const statusText = player.is_alive !== false ? 'Жив' : 'Мёртв';
        
        return `
            <div class="player-item ${isSelf ? 'is-self' : ''}">
                <div class="player-avatar ${avatarClass}">${initial}</div>
                <div class="player-info">
                    <div class="player-name">${player.nickname || 'Unknown'}</div>
                    <div class="player-role">${player.is_ai ? 'AI' : 'Человек'}</div>
                </div>
                <div class="player-status ${statusClass}">${statusText}</div>
            </div>
        `;
    }).join('');
    
    // Обновляем селекты для действий
    updateTargetSelects();
}

function updateTargetSelects() {
    const alivePlayers = players.filter(p => p.is_alive !== false && p.player_id !== myPlayerId);
    
    // Ночные действия
    els.selectNightTarget.innerHTML = '<option value="">Выберите игрока</option>' + 
        alivePlayers.map(p => `<option value="${p.player_id}">${p.nickname}</option>`).join('');
    
    // Голосование
    els.selectVoteTarget.innerHTML = '<option value="">Выберите игрока</option>' + 
        alivePlayers.map(p => `<option value="${p.player_id}">${p.nickname}</option>`).join('');
}

els.btnRefreshPlayers.addEventListener('click', async () => {
    const roomId = els.inputRoomId.value.trim();
    if (!roomId) return;
    
    try {
        const data = await apiRequest(`/api/rooms/${roomId}/players`);
        players = data.players || data || [];
        updatePlayersList();
        log(`Получено игроков: ${players.length}`, 'info');
    } catch (e) {
        log(`Ошибка получения игроков: ${e.message}`, 'error');
    }
});

// ==================== WEBSOCKET ====================

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
        
        updateWsUI('connecting');
        
        const wsUrl = `${WS_BASE_URL}/ws/rooms/${roomId}?token=${token}`;
        log(`Подключение к WS: ${wsUrl}`, 'info');
        
        ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            log('WebSocket соединение установлено', 'success');
            updateWsUI('connected');
            reconnectAttempts = 0;
            resolve();
        };
        
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleWsMessage(data);
            } catch (e) {
                log(`Получено WS (raw): ${event.data}`, 'ws-recv');
            }
        };
        
        ws.onclose = (event) => {
            log(`WebSocket отключен. Код: ${event.code}`, 'warning');
            updateWsUI('disconnected');
            ws = null;
            
            // Автоматическое переподключение
            if (reconnectAttempts < maxReconnectAttempts && currentSessionToken) {
                reconnectAttempts++;
                log(`Переподключение через 3 сек... (попытка ${reconnectAttempts})`, 'warning');
                setTimeout(() => connectToWebSocket().catch(() => {}), 3000);
            }
        };
        
        ws.onerror = (error) => {
            log('WebSocket ошибка', 'error');
            updateWsUI('disconnected');
            reject(error);
        };
    });
}

function updateWsUI(status) {
    els.wsStatusIndicator.className = `status-indicator ${status}`;
    els.wsStatusText.textContent = status === 'connected' ? 'Подключено' : 
                                    status === 'connecting' ? 'Подключение...' : 'Отключено';
    
    els.btnWsConnect.disabled = status === 'connected';
    els.btnWsDisconnect.disabled = status !== 'connected';
    els.btnWsReady.disabled = status !== 'connected';
    els.btnWsChat.disabled = status !== 'connected';
}

function sendWsMessage(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
        log(`WS отправлено: ${data.type || data.event}`, 'ws-send', data);
    } else {
        log('WebSocket не подключен', 'error');
    }
}

function handleWsMessage(data) {
    // Проверяем, является ли сообщение от ИИ
    let isAIMessage = false;
    
    if (data.is_ai === true || data.from_ai === true) {
        isAIMessage = true;
    } else if (data.data && (data.data.is_ai === true || data.data.from_ai === true)) {
        isAIMessage = true;
    } else if (data.player && data.player.is_ai === true) {
        isAIMessage = true;
    }
    
    // Пропускаем сообщения от ИИ если выключено
    if ((isAIMessage || data.event === 'chat_message' || data.type === 'chat_message') && !showAIMessages) {
        return;
    }
    
    const eventType = data.type || data.event || 'unknown';
    log(`WS получено: ${eventType}`, 'ws-recv', data, isAIMessage);
    
    // Обработка различных событий
    switch (eventType) {
        case 'player_joined':
        case 'player_joined_event':
            handlePlayerJoined(data);
            break;
            
        case 'player_left':
            handlePlayerLeft(data);
            break;
            
        case 'game_started':
            handleGameStarted(data);
            break;
            
        case 'phase_changed':
        case 'night_started':
        case 'day_started':
        case 'voting_started':
            handlePhaseChanged(data);
            break;
            
        case 'role_assigned':
            handleRoleAssigned(data);
            break;
            
        case 'chat_event':
        case 'chat_message':
        case 'chat_event_extended':
            handleChatMessage(data);
            break;
            
        case 'vote_received':
        case 'vote_update':
            handleVoteUpdate(data);
            break;
            
        case 'vote_ended':
            handleVoteEnded(data);
            break;
            
        case 'you_died':
            handlePlayerDied(data);
            break;
            
        case 'turing_test_started':
            handleTuringTestStarted(data);
            break;
            
        case 'turing_test_result':
        case 'turing_test_results':
            handleTuringTestResults(data);
            break;
            
        case 'game_over':
        case 'game_ended':
            handleGameOver(data);
            break;
            
        case 'investigation_result':
            handleInvestigationResult(data);
            break;
            
        case 'error':
            log(`Ошибка от сервера: ${data.error || data.message}`, 'error');
            break;
    }
}

// Обработчики событий

function handlePlayerJoined(data) {
    const playerId = data.player_id || (data.data && data.data.player_id);
    const nickname = data.nickname || (data.data && data.data.nickname);
    const isAI = data.is_ai || (data.data && data.data.is_ai);
    
    // Добавляем в список если нет
    const existingIndex = players.findIndex(p => p.player_id === playerId);
    if (existingIndex === -1) {
        players.push({
            player_id: playerId,
            nickname: nickname,
            is_ai: isAI,
            is_alive: true
        });
    }
    
    updatePlayersList();
    addSystemMessage(`${nickname} присоединился к комнате`);
}

function handlePlayerLeft(data) {
    const playerId = data.player_id || (data.data && data.data.player_id);
    const nickname = data.nickname || (data.data && data.data.nickname);
    
    players = players.filter(p => p.player_id !== playerId);
    updatePlayersList();
    addSystemMessage(`${nickname} покинул комнату`);
}

function handleGameStarted(data) {
    currentPhase = 'night';
    currentDay = 1;
    updateGameInfo();
    addSystemMessage('Игра началась! Распределение ролей...');
    
    // Показываем кнопки действий
    els.btnWsStart.disabled = true;
}

function handlePhaseChanged(data) {
    const phaseData = data.data || data;
    currentPhase = phaseData.phase || data.type;
    currentDay = phaseData.day_number || currentDay;
    
    updateGameInfo();
    updateChatTabs();
    
    // Показываем/скрываем действия
    if (currentPhase === 'night') {
        els.nightActions.style.display = 'block';
        els.votingActions.style.display = 'none';
        addSystemMessage(`Наступила ночь. День ${currentDay}`);
    } else if (currentPhase === 'day' || currentPhase === 'voting') {
        els.nightActions.style.display = 'none';
        els.votingActions.style.display = 'block';
        addSystemMessage(`Наступил день ${currentDay}. Время голосования!`);
    } else {
        els.nightActions.style.display = 'none';
        els.votingActions.style.display = 'none';
    }
}

function handleRoleAssigned(data) {
    const roleData = data.data || data;
    currentRole = roleData.role;
    
    els.displayRole.textContent = getRoleName(currentRole);
    els.displayRole.className = `game-info-value role-badge ${currentRole}`;
    
    addSystemMessage(`Ваша роль: ${getRoleName(currentRole)}`);
    
    // Показываем доступные чаты
    updateChatTabs();
}

function handleChatMessage(data) {
    const chatData = data.data || data;
    const chatName = data.chatName || chatData.chatName || 'cityGroup';
    
    // Фильтруем по активному чату
    if (chatName !== activeChat) return;
    
    const playerId = data.player_id || chatData.player_id;
    const nickname = data.nickname || chatData.nickname || 'Unknown';
    const content = data.content || data.body || chatData.content || '';
    const isAI = data.is_ai || chatData.is_ai;
    const isOwn = playerId === myPlayerId;
    
    addChatMessage(nickname, content, isAI, isOwn);
}

function handleVoteUpdate(data) {
    const voteData = data.data || data;
    // Показываем результаты голосования
    showVotingResults(voteData.vote_count || voteData.votes);
}

function handleVoteEnded(data) {
    const voteData = data.data || data;
    const eliminatedId = data.eliminated_player_id || voteData.eliminated_player_id;
    
    const eliminated = players.find(p => p.player_id === eliminatedId);
    if (eliminated) {
        eliminated.is_alive = false;
        updatePlayersList();
        addSystemMessage(`${eliminated.nickname} был исключён!`);
    }
    
    els.votingResults.style.display = 'none';
}

function handlePlayerDied(data) {
    isAlive = false;
    els.displayStatus.textContent = 'Мёртв';
    els.displayStatus.className = 'game-info-value status-badge dead';
    
    const msg = data.data?.message || data.message || 'Вы погибли!';
    addSystemMessage(msg);
    
    updatePlayersList();
}

function handleTuringTestStarted(data) {
    const testData = data.data || data;
    els.turingTestSection.style.display = 'block';
    els.winnerSection.style.display = 'none';
    
    const playersList = testData.players || [];
    renderTuringTest(playersList);
    
    addSystemMessage('Начался Turing Test! Определите AI игроков.');
}

function handleTuringTestResults(data) {
    const results = data.data || data;
    els.turingTestSection.style.display = 'none';
    
    const accuracy = results.accuracy || results.detection_accuracy || 0;
    addSystemMessage(`Turing Test завершён! Точность: ${Math.round(accuracy * 100)}%`);
}

function handleGameOver(data) {
    const gameData = data.data || data;
    const winner = gameData.winner;
    
    currentPhase = 'finished';
    updateGameInfo();
    
    els.winnerSection.style.display = 'block';
    els.winnerTeam.textContent = getWinnerText(winner);
    
    addSystemMessage(`Игра окончена! Победили: ${getWinnerText(winner)}`);
}

function handleInvestigationResult(data) {
    const invData = data.data || data;
    const targetRole = invData.target_role || invData.role;
    const isMafia = invData.is_mafia;
    
    const target = players.find(p => p.player_id === invData.target_id);
    const targetName = target ? target.nickname : 'Игрок';
    
    addSystemMessage(`Результат проверки: ${targetName} - ${isMafia ? 'МАФИЯ!' : 'Мирный'}`);
}

// ==================== UI ФУНКЦИИ ====================

function updateGameInfo() {
    els.displayPhase.textContent = currentPhase.toUpperCase();
    els.displayDay.textContent = currentDay > 0 ? currentDay : '-';
    els.displayRole.textContent = currentRole ? getRoleName(currentRole) : '-';
    els.displayStatus.textContent = isAlive ? 'В игре' : 'Мёртв';
    els.displayStatus.className = `game-info-value status-badge ${isAlive ? '' : 'dead'}`;
}

function updateChatTabs() {
    const tabs = [
        { id: 'tab-cityGroup', chat: 'cityGroup', always: true },
        { id: 'tab-mafiaGroup', chat: 'mafiaGroup', roles: ['mafia'] },
        { id: 'tab-roleChat', chat: 'roleChat', roles: ['doctor', 'commissioner'] }
    ];
    
    tabs.forEach(tab => {
        const el = document.getElementById(tab.id);
        let enabled = false;
        
        if (tab.always) {
            enabled = true;
        } else if (tab.roles.includes(currentRole)) {
            enabled = currentPhase === 'night';
        }
        
        if (enabled) {
            el.classList.remove('disabled');
            el.querySelector('.tab-status').textContent = 'Активен';
            el.querySelector('.tab-status').classList.remove('inactive');
        } else {
            el.classList.add('disabled');
            el.querySelector('.tab-status').textContent = 'Недоступен';
            el.querySelector('.tab-status').classList.add('inactive');
        }
    });
}

function getRoleName(role) {
    const roles = {
        'civilian': 'Мирный',
        'mafia': 'Мафия',
        'doctor': 'Доктор',
        'commissioner': 'Комиссар'
    };
    return roles[role] || role;
}

function getWinnerText(winner) {
    const winners = {
        'mafia': 'Мафия',
        'civilians': 'Мирные',
        'aborted': 'Игра прервана'
    };
    return winners[winner] || winner;
}

function addChatMessage(sender, content, isAI, isOwn) {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    const messageEl = document.createElement('div');
    messageEl.className = `chat-message ${isOwn ? 'own' : 'other'}`;
    
    let header = `<span class="message-sender">${sender}</span>`;
    if (isAI) {
        header += `<span class="message-ai-badge">AI</span>`;
    }
    header += `<span class="message-time">${time}</span>`;
    
    messageEl.innerHTML = `
        <div class="message-header">${header}</div>
        <div class="message-content">${content}</div>
    `;
    
    els.chatMessages.appendChild(messageEl);
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

function addSystemMessage(content) {
    addChatMessage('Система', content, false, false);
}

function showVotingResults(voteCount) {
    if (!voteCount) return;
    
    els.votingResults.style.display = 'block';
    const maxVotes = Math.max(...Object.values(voteCount));
    
    let html = '';
    for (const [playerId, votes] of Object.entries(voteCount)) {
        const player = players.find(p => p.player_id == playerId);
        const name = player ? player.nickname : `Player ${playerId}`;
        const percent = maxVotes > 0 ? (votes / maxVotes) * 100 : 0;
        
        html += `
            <div class="vote-bar">
                <span class="vote-bar-name">${name}</span>
                <div class="vote-bar-track">
                    <div class="vote-bar-fill" style="width: ${percent}%"></div>
                </div>
                <span class="vote-bar-count">${votes}</span>
            </div>
        `;
    }
    
    document.getElementById('vote-bars').innerHTML = html;
}

function renderTuringTest(playersList) {
    const container = document.getElementById('turing-players-list');
    
    container.innerHTML = playersList.map(player => `
        <div class="turing-player" data-player-id="${player.id}">
            <span class="turing-player-name">${player.nickname}</span>
            <div class="turing-vote-btns">
                <button class="turing-vote-btn human" data-vote="human">Человек</button>
                <button class="turing-vote-btn ai" data-vote="ai">AI</button>
            </div>
        </div>
    `).join('');
    
    // Обработчики кнопок
    container.querySelectorAll('.turing-vote-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const playerEl = e.target.closest('.turing-player');
            const playerId = playerEl.dataset.playerId;
            const vote = e.target.dataset.vote;
            
            // Убираем выбор у всех кнопок этого игрока
            playerEl.querySelectorAll('.turing-vote-btn').forEach(b => b.style.opacity = '0.5');
            e.target.style.opacity = '1';
            
            // Сохраняем выбор
            playerEl.dataset.vote = vote;
        });
    });
}

// ==================== ОБРАБОТЧИКИ КНОПОК ====================

// Подключение к WebSocket
els.btnWsConnect.addEventListener('click', async () => {
    try {
        await connectToWebSocket();
    } catch (e) {
        log(`Ошибка подключения: ${e.message}`, 'error');
    }
});

els.btnWsDisconnect.addEventListener('click', () => {
    if (ws) {
        ws.close();
    }
});

// Готов
els.btnWsReady.addEventListener('click', () => {
    sendWsMessage({ type: 'ready' });
    addSystemMessage('Вы отметились как готовый');
});

// Начать игру (хост)
els.btnWsStart.addEventListener('click', async () => {
    const roomId = els.inputRoomId.value.trim();
    if (!roomId) return;
    
    try {
        const data = await apiRequest(`/api/rooms/${roomId}/game/start`, 'POST', {});
        log(`Игра началась!`, 'success');
    } catch (e) {
        log(`Ошибка запуска игры: ${e.message}`, 'error');
    }
});

// Отправка сообщения
els.btnWsChat.addEventListener('click', sendChatMessage);
els.inputChatMsg.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendChatMessage();
});

function sendChatMessage() {
    const content = els.inputChatMsg.value.trim();
    if (!content) return;
    
    const message = {
        type: 'chat_message',
        chatName: activeChat,
        content: content
    };
    
    sendWsMessage(message);
    els.inputChatMsg.value = '';
}

// Переключение чатов
document.querySelectorAll('.chat-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        if (tab.classList.contains('disabled')) return;
        
        document.querySelectorAll('.chat-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        
        activeChat = tab.dataset.chat;
        log(`Переключен чат на: ${activeChat}`, 'info');
    });
});

// Ночные действия
els.btnWsNightAction.addEventListener('click', () => {
    const action = els.selectNightAction.value;
    const targetId = els.selectNightTarget.value;
    
    if (!targetId) return log('Выберите цель', 'error');
    
    const message = {
        type: 'night_action',
        action: action,
        target_id: parseInt(targetId)
    };
    
    sendWsMessage(message);
    addSystemMessage(`Выполнено действие: ${action} на игрока ${targetId}`);
});

// Голосование
els.btnWsVote.addEventListener('click', () => {
    const targetId = els.selectVoteTarget.value;
    
    if (!targetId) return log('Выберите игрока для голосования', 'error');
    
    const message = {
        type: 'vote',
        target_id: parseInt(targetId)
    };
    
    sendWsMessage(message);
    addSystemMessage(`Вы проголосовали за игрока ${targetId}`);
});

// Turing Test
els.btnSubmitTuring.addEventListener('click', () => {
    const votes = {};
    
    document.querySelectorAll('.turing-player').forEach(playerEl => {
        const playerId = playerEl.dataset.playerId;
        const vote = playerEl.dataset.vote;
        if (vote) {
            votes[playerId] = vote === 'ai';
        }
    });
    
    const message = {
        type: 'turing_test_vote',
        votes: votes
    };
    
    sendWsMessage(message);
    addSystemMessage('Результаты Turing Test отправлены');
    els.turingTestSection.style.display = 'none';
});

// ==================== ИНИЦИАЛИЗАЦИЯ ====================

log('Тестовый интерфейс загружен', 'info');
updateGameInfo();
updateChatTabs();