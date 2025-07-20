async function sendMessage() {
    const userInput = document.getElementById('userInput').value;
    if (!userInput) return;

    const chatLog = document.getElementById('chatlog');

    // Add user's message to chat log
    const userMessage = document.createElement('div');
    userMessage.className = 'user';
    userMessage.textContent = userInput;
    chatLog.appendChild(userMessage);

    document.getElementById('userInput').value = '';

    // Send message to server
    try {
        const response = await fetch('/get', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ msg: userInput })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }

        const data = await response.json();

        // Add bot's response to chat log
        const botMessage = document.createElement('div');
        botMessage.className = 'bot';
        botMessage.textContent = data.response || data.error || 'No response';
        chatLog.appendChild(botMessage);

        // Scroll chat log to the bottom
        chatLog.scrollTop = chatLog.scrollHeight;
    } catch (error) {
        console.error('Error occurred:', error);
        alert('An error occurred while sending the message.');
    }
}
