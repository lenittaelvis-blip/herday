// Splash screen
window.addEventListener("load", function () {
    const splash = document.getElementById("splash-screen");
    const mainApp = document.getElementById("main-app");

    setTimeout(function () {
        splash.style.opacity = "0";
        splash.style.transition = "opacity 0.8s ease";

        setTimeout(function () {
            splash.style.display = "none";
            mainApp.style.display = "flex";
            mainApp.style.opacity = "0";
            mainApp.style.transition = "opacity 0.8s ease";

            setTimeout(function () {
                mainApp.style.opacity = "1";
            }, 50);
        }, 800);
    }, 2000);
});

let latestScheduleText = "";

function escapeHtml(value) {
    return value
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function addUserMessage(message) {
    const chatBox = document.getElementById("chat-box");
    const userDiv = document.createElement("div");
    userDiv.className = "user";
    userDiv.innerHTML = `<strong>You:</strong> ${escapeHtml(message)}`;
    chatBox.appendChild(userDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function typeWriterEffect(text) {
    const chatBox = document.getElementById("chat-box");

    const botDiv = document.createElement("div");
    botDiv.className = "bot";
    botDiv.innerHTML = "<strong>HerDay:</strong><br>";

    const textSpan = document.createElement("span");
    botDiv.appendChild(textSpan);
    chatBox.appendChild(botDiv);

    let index = 0;

    function type() {
        if (index < text.length) {
            if (text.charAt(index) === "\n") {
                textSpan.innerHTML += "<br>";
            } else {
                textSpan.innerHTML += escapeHtml(text.charAt(index));
            }

            index += 1;
            chatBox.scrollTop = chatBox.scrollHeight;
            setTimeout(type, 15);
        }
    }

    type();
}

function maybeCaptureSchedule(text) {
    const normalized = text.replace(/[–—]/g, "-");
    const lines = text.split("\n").map(function (line) {
        return line.trim();
    });
    const timedLineCount = lines.filter(function (line) {
        return /^\d{1,2}(:\d{2})?\s?(AM|PM)\s*-\s/i.test(line.replace(/[–—]/g, "-"));
    }).length;
    const scheduleKeywords = ["wake up", "breakfast", "start work", "lunch", "dinner", "bedtime", "sleep"];
    const keywordHits = scheduleKeywords.filter(function (word) {
        return normalized.toLowerCase().includes(word);
    }).length;
    const looksLikeSchedule =
        timedLineCount >= 3 ||
        /daily schedule|schedule based on what you shared|plan your day/i.test(normalized) ||
        keywordHits >= 3;

    if (!looksLikeSchedule) {
        return;
    }

    latestScheduleText = text;
    const downloadBtn = document.getElementById("download-schedule-btn");
    if (downloadBtn) {
        downloadBtn.disabled = false;
    }
}

function closeMood(animated) {
    const moodContainer = document.querySelector(".mood-container");
    if (!moodContainer) {
        return;
    }

    if (animated) {
        moodContainer.classList.add("fade-out");
        setTimeout(function () {
            moodContainer.style.display = "none";
        }, 500);
    } else {
        moodContainer.style.display = "none";
    }
}

function closeTasks() {
    const tasksContainer = document.querySelector(".tasks-container");
    if (!tasksContainer) {
        return;
    }
    tasksContainer.style.display = "none";
}

async function sendMood(mood) {
    let moodMessage = "";

    if (mood === "happy") moodMessage = "I'm feeling happy today!";
    if (mood === "low") moodMessage = "I'm feeling a little low today.";
    if (mood === "overwhelmed") moodMessage = "I'm feeling overwhelmed today.";
    if (mood === "motivated") moodMessage = "I'm feeling motivated today.";

    if (!moodMessage) {
        return;
    }

    addUserMessage(moodMessage);

    try {
        const response = await fetch("/mood", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mood: mood })
        });

        const data = await response.json();
        typeWriterEffect(data.reply || "Tell me more about how you're feeling.");
    } catch (error) {
        typeWriterEffect("Something went wrong.");
    }

    closeMood(true);
}

async function sendMessage() {
    const input = document.getElementById("user-input");
    const message = input.value.trim();

    if (!message) {
        return;
    }

    addUserMessage(message);
    input.value = "";

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: message })
        });

        const data = await response.json();
        if (data.reply) {
            typeWriterEffect(data.reply);
            maybeCaptureSchedule(data.reply);
        }
    } catch (error) {
        typeWriterEffect("Something went wrong. Please try again.");
    }
}

function renderTasks(tasks) {
    const list = document.getElementById("task-list");
    if (!list) {
        return;
    }

    if (!tasks.length) {
        list.innerHTML = '<p class="task-empty">No tasks yet.</p>';
        return;
    }

    list.innerHTML = tasks
        .map(function (task) {
            const doneClass = task.is_done ? "task-item done" : "task-item";
            const checked = task.is_done ? "checked" : "";
            const safeTitle = escapeHtml(task.title);
            return `
                <div class="${doneClass}">
                    <label>
                        <input type="checkbox" ${checked} onchange="toggleTask(${task.id}, this.checked)">
                        <span>${safeTitle}</span>
                    </label>
                    <button class="delete-task" onclick="deleteTask(${task.id})">Delete</button>
                </div>
            `;
        })
        .join("");
}

async function loadTasks() {
    try {
        const response = await fetch("/tasks");
        const data = await response.json();
        renderTasks(data.tasks || []);
    } catch (error) {
        const list = document.getElementById("task-list");
        if (list) {
            list.innerHTML = '<p class="task-empty">Unable to load tasks.</p>';
        }
    }
}

async function addTask() {
    const input = document.getElementById("task-input");
    if (!input) {
        return;
    }

    const title = input.value.trim();
    if (!title) {
        return;
    }

    try {
        await fetch("/tasks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: title })
        });
        input.value = "";
        await loadTasks();
    } catch (error) {
        typeWriterEffect("Could not add the task right now.");
    }
}

async function toggleTask(taskId, isDone) {
    try {
        await fetch(`/tasks/${taskId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ is_done: isDone })
        });
        await loadTasks();
    } catch (error) {
        typeWriterEffect("Could not update the task right now.");
    }
}

async function deleteTask(taskId) {
    try {
        await fetch(`/tasks/${taskId}`, { method: "DELETE" });
        await loadTasks();
    } catch (error) {
        typeWriterEffect("Could not delete the task right now.");
    }
}

document.addEventListener("DOMContentLoaded", function () {
    const inputField = document.getElementById("user-input");
    if (inputField) {
        inputField.addEventListener("keydown", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                sendMessage();
            }
        });
    }

    const taskInput = document.getElementById("task-input");
    if (taskInput) {
        taskInput.addEventListener("keydown", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                addTask();
            }
        });
    }

    loadTasks();
});
