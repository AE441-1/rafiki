let installPrompt = null;
const installButton = document.getElementById("install-app");

if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/service-worker.js", { scope: "/" })
        .catch((error) => console.warn("Rafiki offline support could not start.", error));
}

window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPrompt = event;
    if (installButton) {
        installButton.hidden = false;
    }
});

if (installButton) {
    installButton.addEventListener("click", async () => {
        if (!installPrompt) {
            return;
        }

        installPrompt.prompt();
        await installPrompt.userChoice;
        installPrompt = null;
        installButton.hidden = true;
    });
}

window.addEventListener("appinstalled", () => {
    if (installButton) {
        installButton.hidden = true;
    }
});