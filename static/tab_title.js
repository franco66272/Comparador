(function () {
    const mensajes = [
        'TecnoRadar - Compará precios',
        'TecnoRadar - ¿Encontraste una oferta?',
        'TecnoRadar - ¡Mirá estos precios!',
        'TecnoRadar - ¿Bajó de precio?',
        'TecnoRadar - Buscá tecnología',
        'TecnoRadar - Compará y ahorrá',
        'TecnoRadar - Te estamos esperando',
        'TecnoRadar - ¿Qué estás buscando?',
    ];

    function aplicarLogo() {
        document.querySelectorAll('.brand-mark').forEach(function (elemento) {
            elemento.innerHTML = `
                <svg class="tecnoradar-logo-icon" viewBox="0 0 48 48" aria-hidden="true" focusable="false">
                    <circle cx="24" cy="24" r="17" fill="none" stroke="#38bdf8" stroke-width="3" opacity="0.95"/>
                    <circle cx="24" cy="24" r="10" fill="none" stroke="#2563eb" stroke-width="3" opacity="0.95"/>
                    <circle cx="24" cy="24" r="3.5" fill="#22c55e"/>
                    <path d="M24 24 L39 11 A21 21 0 0 1 42 18 Z" fill="#38bdf8"/>
                    <path d="M24 24 L35 35" stroke="#2563eb" stroke-width="3" stroke-linecap="round"/>
                </svg>`;
            elemento.style.width = '36px';
            elemento.style.height = '36px';
            elemento.style.borderRadius = '0';
            elemento.style.background = 'transparent';
            elemento.style.fontSize = '0';
            elemento.style.display = 'inline-flex';
            elemento.style.flexShrink = '0';
        });
    }

    let indice = 0;
    let temporizador = null;

    function cambiarTitulo() {
        document.title = mensajes[indice];
        indice = (indice + 1) % mensajes.length;
    }

    function iniciarTituloDinamico() {
        aplicarLogo();
        cambiarTitulo();
        temporizador = window.setInterval(cambiarTitulo, 2200);

        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                if (temporizador) {
                    clearInterval(temporizador);
                    temporizador = null;
                }
            } else if (!temporizador) {
                cambiarTitulo();
                temporizador = window.setInterval(cambiarTitulo, 2200);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciarTituloDinamico, { once: true });
    } else {
        iniciarTituloDinamico();
    }
})();
