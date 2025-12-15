let timerInterval;
let elapsedSeconds = 0;
let activePlayer = null;
let foulPoints = 0;
let nextPlayerId = null;
let lastPottedRed = false;
let redBallsPottedThisTurn = 0;
let redBallAdjustment = 0;
let undoStack = [];
let redoStack = [];
let gameState = {
    activePlayer: null,
    lastPottedRed: false,
    redBallsPottedThisTurn: 0
};
let currentBreak = 0;
let isFreeBall = false;
let lastShotWasFreeBall = false;


function recordAction(action) {
    const actionWithState = {
        ...action,
        ballsVisibility: getBallsVisibilityState(),
        pointsOnTable: parseInt(document.getElementById("points-on-table").textContent, 10),
        redBallCount: parseInt(document.getElementById("red-ball-count").textContent, 10),
        lastPottedRed: gameState.lastPottedRed,
        redBallsPottedThisTurn: gameState.redBallsPottedThisTurn
    };

    console.log(actionWithState);
    undoStack.push(actionWithState);
    redoStack = [];
}

function undo() {
    if (undoStack.length === 0) return;

    const lastAction = undoStack.pop();
    console.log("Undoing action:", lastAction);
    redoStack.push(lastAction);

    if (lastAction.type === "updateScore") {
        currentBreak = lastAction.previousBreak;
        updateBreakDisplay();

        if (lastAction.wasFreeBall) {
            isFreeBall = true;
        }

        if (lastAction.previousLastShotWasFreeBall !== undefined) {
            lastShotWasFreeBall = lastAction.previousLastShotWasFreeBall;
        }
    }

    switch (lastAction.type) {
        case "updateActivePlayer":
            if (lastAction.previousPlayerId !== null) {
                gameState.activePlayer = parseInt(lastAction.previousPlayerId, 10);
                activePlayer = gameState.activePlayer;

                document.querySelectorAll(".set-active-player").forEach(button => {
                    button.classList.remove("active");
                });
                const activeButton = document.querySelector(`.set-active-player[data-player="${gameState.activePlayer}"]`);
                if (activeButton) {
                    activeButton.classList.add("active");
                }

                const playerHeaders = document.querySelectorAll("h4");
                playerHeaders.forEach(header => {
                    header.innerHTML = header.innerHTML.replace(" 🔴", "");
                });
                if (gameState.activePlayer === 1) {
                    playerHeaders[0].innerHTML += " 🔴";
                } else if (gameState.activePlayer === 2) {
                    playerHeaders[1].innerHTML += " 🔴";
                }
            }

            if (lastAction.ballsVisibility) {
                restoreBallsVisibilityState(lastAction.ballsVisibility);
            }

            if (lastAction.pointsOnTable) {
                document.getElementById("points-on-table").textContent = lastAction.pointsOnTable;
            }

            if (lastAction.redBallCount !== undefined) {
                document.getElementById("red-ball-count").textContent = lastAction.redBallCount;
                updateRedBallsUI(lastAction.redBallCount);
            }
            break;

        case "updateScore":
            const playerScoreInput = document.querySelector(
                `.player-score[data-player="${lastAction.playerId}"]`
            );
            if (playerScoreInput) {
                playerScoreInput.value = lastAction.previousScore;
            }

            if (lastAction.redBallsChange) {
                const redBallsElement = document.getElementById("red-ball-count");
                if (redBallsElement) {
                    redBallsElement.textContent = lastAction.previousRedBalls;
                    updateRedBallsUI(lastAction.previousRedBalls);
                }
            }

            const pointsOnTableElement = document.getElementById("points-on-table");
            if (pointsOnTableElement) {
                pointsOnTableElement.textContent = lastAction.previousPointsOnTable;
                hideColorBallBasedOnPoints(lastAction.previousPointsOnTable);
            }

            if (lastAction.ballsVisibility) {
                restoreBallsVisibilityState(lastAction.ballsVisibility);
            }

            gameState.lastPottedRed = lastAction.lastPottedRed || false;
            gameState.redBallsPottedThisTurn = lastAction.redBallsPottedThisTurn || 0;
            break;

        case "foul":
            const opponentScoreElement = document.querySelector(
                `.player-score[data-player="${lastAction.opponentId}"]`
            );
            if (opponentScoreElement) {
                opponentScoreElement.value = lastAction.previousOpponentScore;
            }

            if (lastAction.redBallsChange) {
                const redBallsElement = document.getElementById("red-ball-count");
                if (redBallsElement) {
                    redBallsElement.textContent = lastAction.previousRedBalls;
                    updateRedBallsUI(lastAction.previousRedBalls);
                }

                const pointsOnTableElement = document.getElementById("points-on-table");
                if (pointsOnTableElement) {
                    pointsOnTableElement.textContent = lastAction.previousPointsOnTable;
                    hideColorBallBasedOnPoints(lastAction.previousPointsOnTable);
                }
            }

            if (lastAction.ballsVisibility) {
                restoreBallsVisibilityState(lastAction.ballsVisibility);
            }

            isFreeBall = false;

            if (lastAction.previousBreak !== undefined) {
                currentBreak = lastAction.previousBreak;
                updateBreakDisplay();
            }

            break;
    }
}

function redo() {
    if (redoStack.length === 0) return;

    const lastUndone = redoStack.pop();
    console.log("Redoing action:", lastUndone);
    undoStack.push(lastUndone);

    if (lastUndone.type === "updateScore") {
        currentBreak = lastUndone.newBreak;
        updateBreakDisplay();

        if (lastUndone.wasFreeBall) {
            isFreeBall = false;
        }
    }

    switch (lastUndone.type) {
        case "updateActivePlayer":
            gameState.activePlayer = parseInt(lastUndone.playerId, 10);
            activePlayer = gameState.activePlayer;

            document.querySelectorAll(".set-active-player").forEach(button => {
                button.classList.remove("active");
            });
            const activeButton = document.querySelector(`.set-active-player[data-player="${gameState.activePlayer}"]`);
            if (activeButton) {
                activeButton.classList.add("active");
            }

            const playerHeaders = document.querySelectorAll("h4");
            playerHeaders.forEach(header => {
                header.innerHTML = header.innerHTML.replace(" 🔴", "");
            });
            if (gameState.activePlayer === 1) {
                playerHeaders[0].innerHTML += " 🔴";
            } else if (gameState.activePlayer === 2) {
                playerHeaders[1].innerHTML += " 🔴";
            }

            if (lastUndone.ballsVisibility) {
                restoreBallsVisibilityState(lastUndone.ballsVisibility);
            }

            if (lastUndone.pointsOnTable) {
                document.getElementById("points-on-table").textContent = lastUndone.pointsOnTable;
            }
            if (lastUndone.redBallCount !== undefined) {
                document.getElementById("red-ball-count").textContent = lastUndone.redBallCount;
                updateRedBallsUI(lastUndone.redBallCount);
            }
            break;

        case "updateScore":
            const playerScoreInput = document.querySelector(
                `.player-score[data-player="${lastUndone.playerId}"]`
            );
            if (playerScoreInput) {
                playerScoreInput.value = lastUndone.newScore;
            }

            if (lastUndone.redBallsChange) {
                const redBallsElement = document.getElementById("red-ball-count");
                if (redBallsElement) {
                    redBallsElement.textContent = lastUndone.newRedBalls;
                    updateRedBallsUI(lastUndone.newRedBalls);
                }
            }

            const pointsOnTableElement = document.getElementById("points-on-table");
            if (pointsOnTableElement) {
                pointsOnTableElement.textContent = lastUndone.newPointsOnTable;
                hideColorBallBasedOnPoints(lastUndone.newPointsOnTable);
            }

            if (lastUndone.ballsVisibility) {
                restoreBallsVisibilityState(lastUndone.ballsVisibility);
            }

            gameState.lastPottedRed = lastUndone.lastPottedRed || false;
            gameState.redBallsPottedThisTurn = lastUndone.redBallsPottedThisTurn || 0;
            break;

        case "foul":
            const opponentScoreElement = document.querySelector(
                `.player-score[data-player="${lastUndone.opponentId}"]`
            );
            if (opponentScoreElement) {
                opponentScoreElement.value = lastUndone.newOpponentScore;
            }

            if (lastUndone.redBallsChange) {
                const redBallsElement = document.getElementById("red-ball-count");
                if (redBallsElement) {
                    redBallsElement.textContent = lastUndone.newRedBalls;
                    updateRedBallsUI(lastUndone.newRedBalls);
                }

                const pointsOnTableElement = document.getElementById("points-on-table");
                if (pointsOnTableElement) {
                    pointsOnTableElement.textContent = lastUndone.newPointsOnTable;
                    hideColorBallBasedOnPoints(lastUndone.newPointsOnTable);
                }
            }

            if (lastUndone.ballsVisibility) {
                restoreBallsVisibilityState(lastUndone.ballsVisibility);
            }

            if (lastUndone.setFreeBall) {
                isFreeBall = true;
            }
            break;
    }
}

function updateRedBallsUI(redBalls) {
    const redButton = document.querySelector('.btn-danger[aria-label="Red"]');
    const redBallContainer = document.getElementById("red-ball-count").closest('.rounded-circle');

    if (parseInt(redBalls) === 0) {
        if (redButton) redButton.style.display = "none";
        if (redBallContainer) redBallContainer.style.display = "none";
    } else {
        if (redButton) redButton.style.display = "inline-block";
        if (redBallContainer) redBallContainer.style.display = "flex";
    }
}

function resetScores() {
    document.querySelectorAll('.player-score').forEach(input => {
        input.value = 0;
    });
}

function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600).toString().padStart(2, '0');
    const minutes = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
    const secs = (seconds % 60).toString().padStart(2, '0');
    return `${hours}:${minutes}:${secs}`;
}

function startTimer() {
    if (!timerInterval) {
        timerInterval = setInterval(() => {
            elapsedSeconds++;
            document.getElementById("match-timer").textContent = formatTime(elapsedSeconds);
        }, 1000);
    }
}

function pauseTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
}

function stopTimer() {
    $('#endFrameModal').modal('show');
}

function endFrame() {
    pauseTimer();
    $('#endFrameModal').modal('hide');
}

function resetGame() {
    pauseTimer();
    elapsedSeconds = 0;
    document.getElementById("match-timer").textContent = formatTime(elapsedSeconds);

    resetScores();
    activePlayer = null;
    isFreeBall = false;
    lastShowWasFreeBall = false;

    document.querySelectorAll("h4").forEach(header => {
        header.innerHTML = header.innerHTML.replace(" 🔴", "");
    });
    document.querySelectorAll(".set-active-player").forEach(button => {
        button.classList.remove("active");
    });

    resetRedBalls();
    resetPointsOnTable();
    resetBreak();

    document.querySelectorAll('.btn, .rounded-circle').forEach(element => {
        element.style.display = "inline-block";
    });
}

function setActivePlayer(playerId) {
    activePlayer = playerId;
    updateActivePlayerUI(playerId);
}

function updateActivePlayerUI(playerId) {
    const previousActivePlayer = document.querySelector('.set-active-player.active')?.dataset.player;

    recordAction({
        type: 'updateActivePlayer',
        playerId: playerId,
        previousPlayerId: previousActivePlayer || null,
    });

    document.querySelectorAll(".set-active-player").forEach(button => {
        button.classList.remove("active");
    });

    const activeButton = document.querySelector(`.set-active-player[data-player="${playerId}"]`);
    if (activeButton) {
        activeButton.classList.add("active");
    }

    const playerHeaders = document.querySelectorAll("h4");

    playerHeaders.forEach(header => {
        header.innerHTML = header.innerHTML.replace(" 🔴", "");
    });

    if (playerId === 1) {
        playerHeaders[0].innerHTML += " 🔴";
    } else if (playerId === 2) {
        playerHeaders[1].innerHTML += " 🔴";
    }
}

function updateScore(points, ballType) {
    if (activePlayer === null) {
        alert("Please select an active player first!");
        return;
    }

    // --- 1. LOGIKA FREE BALL ---
    let actualPoints = points;
    let effectiveBallType = ballType;
    let wasFreeBallShot = false;

    if (isFreeBall && ballType === 'color') {
        actualPoints = 1;
        effectiveBallType = 'red';
        wasFreeBallShot = true;
    }

    // --- 2. BEZPIECZNE POBIERANIE INPUTA WYNIKU (POPRAWKA) ---
    // Zamiast closest(), używamy konkretnego selektora, który na 100% zadziała
    const playerScoreInput = document.querySelector(`.player-score[data-player="${activePlayer}"]`);

    if (!playerScoreInput) {
        console.error("Critical Error: Score input not found for player " + activePlayer);
        return;
    }

    const previousScore = parseInt(playerScoreInput.value, 10) || 0;
    const newScore = previousScore + actualPoints;

    currentBreak += actualPoints;
    updateBreakDisplay();

    const previousRedBalls = parseInt(document.getElementById("red-ball-count").textContent, 10);
    const previousPointsOnTable = parseInt(document.getElementById("points-on-table").textContent, 10);

    // --- 3. LOGIKA HISTORII (UNDO) ---
    let pointsToRemoveFromTable = 0;
    if (effectiveBallType === 'red' && !wasFreeBallShot) {
        pointsToRemoveFromTable = 8;
    }

    // Zabezpieczenie na wypadek, gdyby zmienna nie była zdefiniowana
    const safeLastShotWasFreeBall = (typeof lastShotWasFreeBall !== 'undefined') ? lastShotWasFreeBall : false;

    recordAction({
        type: "updateScore",
        playerId: activePlayer,
        previousScore: previousScore,
        newScore: newScore,
        ballType: ballType,
        redBallsChange: (effectiveBallType === 'red' && !wasFreeBallShot),
        previousRedBalls: previousRedBalls,
        previousPointsOnTable: previousPointsOnTable,
        newPointsOnTable: previousPointsOnTable - pointsToRemoveFromTable,
        previousBreak: currentBreak - actualPoints,
        newBreak: currentBreak,
        wasFreeBall: wasFreeBallShot,
        previousLastShotWasFreeBall: safeLastShotWasFreeBall
    });

    // --- 4. AKTUALIZACJA UI ---
    playerScoreInput.value = newScore;

    // --- 5. LOGIKA STOŁU I CZERWONYCH ---
    if (effectiveBallType === 'red') {
        for (let i = 0; i < actualPoints; i++) {
            redBallsPottedThisTurn++;

            // Jeśli to zwykła czerwona (nie free ball) -> Zdejmujemy ze stołu
            if (!wasFreeBallShot) {
                updateRedBalls(1);
                updatePointsOnTable(1);
            }

            if (redBallsPottedThisTurn > 1 && !wasFreeBallShot) {
                updatePointsOnTable(7);
            }
        }
        lastPottedRed = true;

        // Ustawiamy flagę globalną
        lastShotWasFreeBall = wasFreeBallShot;

    } else if (ballType === 'color') {
        if (lastPottedRed) {
            // Jeśli to kolor po czerwonej (i poprzedni to nie był Free Ball), zdejmujemy 7 pkt
            if (!safeLastShotWasFreeBall) {
                updatePointsOnTable(7);
            }
            lastShotWasFreeBall = false;
        } else {
            // Koniec gry na kolorach
            updatePointsOnTable(points);
        }
        lastPottedRed = false;
        redBallsPottedThisTurn = 0;
    }

    // --- 6. UKRYWANIE BIL ---
    const currentPointsOnTable = parseInt(document.getElementById("points-on-table").textContent, 10);
    hideColorBallBasedOnPoints(currentPointsOnTable);

    if (currentPointsOnTable <= 27) {
        showColorBalls();
        hideColorBallBasedOnPoints(currentPointsOnTable);
    }

    // --- 7. RESET TRYBU FREE BALL ---
    if (isFreeBall) {
        isFreeBall = false;
    }
}

function resetBreak() {
    currentBreak = 0;

    document.querySelectorAll(".break-container").forEach(container => {
        container.style.display = "none";
    });
    document.querySelectorAll(".player-break").forEach(span => span.textContent = "0");
}

function updateBreakDisplay() {

    document.querySelectorAll(".break-container").forEach(container => {
        const player = parseInt(container.getAttribute("data-player"), 10);

        if (player === activePlayer && currentBreak > 0) {
            container.style.display = "inline";
        } else {
            container.style.display = "none";
        }
    });

    const breakSpan = document.querySelector(`.player-break[data-player="${activePlayer}"]`);
    if (breakSpan) {
        breakSpan.textContent = currentBreak;
    }
}

function hideColorBallBasedOnPoints(pointsOnTable) {
    if (pointsOnTable <= 25) {
        hideColorBall('yellow');
    }
    if (pointsOnTable <= 22) {
        hideColorBall('green');
    }
    if (pointsOnTable <= 18) {
        hideColorBall('brown');
    }
    if (pointsOnTable <= 13) {
        hideColorBall('blue');
    }
    if (pointsOnTable <= 7) {
        hideColorBall('pink');
    }
    if (pointsOnTable === 0) {
        hideColorBall('black');
    }

    hideBallIconBasedOnPoints(pointsOnTable);
}

function hideBallIconBasedOnPoints(pointsOnTable) {
    if (pointsOnTable <= 25) {
        hideBallIcon('yellow');
    }
    if (pointsOnTable <= 22) {
        hideBallIcon('green');
    }
    if (pointsOnTable <= 18) {
        hideBallIcon('brown');
    }
    if (pointsOnTable <= 13) {
        hideBallIcon('blue');
    }
    if (pointsOnTable <= 7) {
        hideBallIcon('pink');
    }
    if (pointsOnTable === 0) {
        hideBallIcon('black');
    }
}

function hideBallIcon(color) {
    const iconElement = document.querySelector(`.rounded-circle.color-ball-marker[data-type="${color}"]`);
    if (iconElement) {
        iconElement.style.display = "none";
    }
}

function hideColorBall(color) {
    const ballElement = document.querySelector(`.color-ball[data-type="${color}"]`);
    if (ballElement) {
        ballElement.classList.add('potted');
        ballElement.style.display = "none";
    }
}

function showColorBalls() {
    const colorBalls = document.querySelectorAll('.color-ball');
    colorBalls.forEach(ball => {
        if (!ball.classList.contains('potted')) {
            ball.style.display = "inline-block";
        }
    });
}

function getBallsVisibilityState() {
    const state = {
        colorBalls: {},
        ballIcons: {},
        redBalls: {
            display: document.getElementById("red-ball-count").closest('.rounded-circle').style.display,
            count: document.getElementById("red-ball-count").textContent
        }
    };

    document.querySelectorAll('.color-ball').forEach(ball => {
        const color = ball.dataset.type;
        state.colorBalls[color] = {
            display: ball.style.display,
            isPotted: ball.classList.contains('potted')
        };
    });

    document.querySelectorAll('.rounded-circle.color-ball-marker').forEach(icon => {
        const color = icon.dataset.type;
        state.ballIcons[color] = {
            display: icon.style.display
        };
    });

    return state;
}

function restoreBallsVisibilityState(state) {
    Object.entries(state.colorBalls).forEach(([color, props]) => {
        const ball = document.querySelector(`.color-ball[data-type="${color}"]`);
        if (ball) {
            ball.style.display = props.display;
            if (props.isPotted) {
                ball.classList.add('potted');
            } else {
                ball.classList.remove('potted');
            }
        }
    });

    Object.entries(state.ballIcons).forEach(([color, props]) => {
        const icon = document.querySelector(`.rounded-circle.color-ball-marker[data-type="${color}"]`);
        if (icon) {
            icon.style.display = props.display;
        }
    });

    if (state.redBalls) {
        const redBallsElement = document.getElementById("red-ball-count");
        redBallsElement.textContent = state.redBalls.count;
        const redBallContainer = redBallsElement.closest('.rounded-circle');
        redBallContainer.style.display = state.redBalls.display;

        const redButton = document.querySelector('.btn-danger[aria-label="Red"]');
        if (redButton) {
            redButton.style.display = state.redBalls.count === "0" ? "none" : "inline-block";
        }
    }
}

function miss() {
    if (activePlayer === null) {
        alert("Please select an active player first!");
        return;
    }

    if (lastPottedRed) {
        updatePointsOnTable(7);
    }

    redBallsPottedThisTurn = 0;
    lastPottedRed = false;
    switchActivePlayer();
}

function safetyShot() {
    if (activePlayer === null) {
        alert("Please select an active player first!");
        return;
    }

    if (lastPottedRed) {
        updatePointsOnTable(7);
    }

    redBallsPottedThisTurn = 0;
    lastPottedRed = false;
    switchActivePlayer();
}

function switchActivePlayer() {
    if (activePlayer === null) {
        alert("No active player to switch!");
        return;
    }

    lastPottedRed = false;
    redBallsPottedThisTurn = 0;
    lastShowWasFreeBall = false;
    resetBreak();

    activePlayer = activePlayer === 1 ? 2 : 1;
    updateActivePlayerUI(activePlayer);
}

function showFoulModal() {
    $('#foulModal').modal('show');

    foulPoints = 0;
    nextPlayerId = null;
    redBallAdjustment = 0;

    document.getElementById('freeBallCheckbox').checked = false;

    document.querySelectorAll('.foul-points').forEach(button => button.classList.remove('active'));
    document.querySelectorAll('.next-player').forEach(button => button.classList.remove('active'));
    document.getElementById('redBallAdjustment').value = 0;
}

document.querySelectorAll('.foul-points').forEach(button => {
    button.addEventListener('click', () => {
        document.querySelectorAll('.foul-points').forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');
        foulPoints = parseInt(button.getAttribute('data-points'));
    });
});

document.querySelectorAll('.next-player').forEach(button => {
    button.addEventListener('click', () => {
        document.querySelectorAll('.next-player').forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');
        nextPlayerId = parseInt(button.getAttribute('data-player'));
    });
});

document.getElementById('redBallAdjustment').addEventListener('input', (e) => {
    const value = parseInt(e.target.value, 10);
    redBallAdjustment = isNaN(value) ? 0 : Math.max(0, Math.min(value, 15));
});

document.getElementById('decreaseRedBalls').addEventListener('click', () => {
    const input = document.getElementById('redBallAdjustment');
    redBallAdjustment = Math.max((parseInt(input.value, 10) || 0) -1, 0);
    input.value = redBallAdjustment;
});

document.getElementById('increaseRedBalls').addEventListener('click', () => {
    const input = document.getElementById('redBallAdjustment');
    redBallAdjustment = Math.min((parseInt(input.value, 10) || 0) + 1, 15);
    input.value = redBallAdjustment;
});

document.getElementById('confirmFoul').addEventListener('click', () => {
    if (foulPoints > 0 && nextPlayerId !== null) {
        const opponentId = activePlayer === 1 ? 2 : 1;
        const opponentScoreElement = document.querySelector(`.player-score[data-player="${opponentId}"]`);
        const previousOpponentScore = parseInt(opponentScoreElement.value || '0', 10);
        const previousRedBalls = parseInt(document.getElementById("red-ball-count").textContent, 10);
        const previousPointsOnTable = parseInt(document.getElementById("points-on-table").textContent, 10);

        // Pobieramy stan checkboxa
        const isFreeBallSelected = document.getElementById('freeBallCheckbox').checked;

        // Zapisujemy obecny break ZANIM go wyzerujemy
        const breakBeforeFoul = currentBreak;

        recordAction({
            type: "foul",
            opponentId: opponentId,
            previousOpponentScore: previousOpponentScore,
            newOpponentScore: previousOpponentScore + foulPoints,
            redBallsChange: redBallAdjustment > 0,
            previousRedBalls: previousRedBalls,
            newRedBalls: previousRedBalls - redBallAdjustment,
            previousPointsOnTable: previousPointsOnTable,
            newPointsOnTable: previousPointsOnTable - (redBallAdjustment * 8),
            setFreeBall: isFreeBallSelected,   // <--- Ważne: tu musi być przecinek
            previousBreak: breakBeforeFoul     // <--- To jest ta nowa linijka
        });

        opponentScoreElement.value = previousOpponentScore + foulPoints;

        if (redBallAdjustment > 0) {
            updateRedBalls(redBallAdjustment);
            updatePointsOnTableForReds(redBallAdjustment);
        }

        if (lastPottedRed) {
            updatePointsOnTable(7);
            lastPottedRed = false;
        }

        redBallsPottedThisTurn = 0;
        lastPottedRed = false;

        // Ustawiamy flagę
        isFreeBall = isFreeBallSelected;

        // Zerujemy breaka (bo zmiana gracza)
        currentBreak = 0;
        updateBreakDisplay();

        setActivePlayer(nextPlayerId);

        $('#foulModal').modal('hide');
    } else {
        alert("Please select foul points and the next player.");
    }
});

function updateRedBalls(points) {
    const redBallsElement = document.getElementById("red-ball-count");
    const redBallContainer = redBallsElement.closest('.rounded-circle');
    const redButton = document.querySelector('.btn-danger[aria-label="Red"]');

    if (redBallsElement) {
        const currentRedBalls = parseInt(redBallsElement.textContent, 10) || 0;
        const newRedBallsCount = Math.max(currentRedBalls - points, 0);
        redBallsElement.textContent = newRedBallsCount;

        if (newRedBallsCount === 0) {
            if (redBallContainer) redBallContainer.style.display = "none";
            if (redButton) redButton.style.display = "none";
        }
    }
}

function updatePointsOnTable(points) {
    const pointsOnTableElement = document.getElementById("points-on-table");
    if (pointsOnTableElement) {
        const currentPoints = parseInt(pointsOnTableElement.textContent, 10) || 0;
        const newPoints = Math.max(currentPoints - points, 0);
        pointsOnTableElement.textContent = newPoints;
    }
}

function updatePointsOnTableForReds(redBallCount) {
    const pointsOnTableElement = document.getElementById("points-on-table");
    if (pointsOnTableElement) {
        const currentPoints = parseInt(pointsOnTableElement.textContent, 10) || 0;
        const pointsToSubtract = redBallCount * 8;
        const newPointsAfterFoul = Math.max(currentPoints - pointsToSubtract, 0);
        pointsOnTableElement.textContent = newPointsAfterFoul;
    }
}

function resetRedBalls() {
    const redBallsElement = document.getElementById("red-ball-count");
    const redBallContainer = redBallsElement.closest('.rounded-circle');
    const redButton = document.querySelector('.btn-danger[aria-label="Red"]');

    if (redBallsElement) {
        redBallsElement.textContent = 15;
    }

    if (redBallContainer) {
        redBallContainer.style.display = "flex";
    }

    if (redButton) {
        redButton.style.display = "inline-block";
    }
}

function resetPointsOnTable() {
    const pointsOnTableElement = document.getElementById("points-on-table");
    if (pointsOnTableElement) {
        pointsOnTableElement.textContent = 147;
    }
}

document.querySelectorAll('.set-active-player').forEach(button => {
    button.addEventListener('click', () => {
        const playerId = parseInt(button.dataset.player, 10);
        setActivePlayer(playerId);
    });
});

document.getElementById('undoButton').addEventListener('click', () => {
    undo();
});

document.getElementById('redoButton').addEventListener('click', () => {
    redo();
});

resetBreak();
