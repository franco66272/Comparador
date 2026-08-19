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

    let indice = 0;
    let temporizador = null;

    function cambiarTitulo() {
        document.title = mensajes[indice];
        indice = (indice + 1) % mensajes.length;
    }

    function aplicarLogoTecnoRadar() {
        const svg = `<svg viewBox="0 0 30 30" width="22" height="22" aria-hidden="true" focusable="false">
            <circle cx="15" cy="15" r="10.5" fill="none" stroke="rgba(255,255,255,.95)" stroke-width="1.6"/>
            <circle cx="15" cy="15" r="5.5" fill="none" stroke="rgba(255,255,255,.55)" stroke-width="1.2"/>
            <path d="M15 15 L23.5 7.5" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>
            <path d="M15 15 L8.2 21.8" stroke="rgba(255,255,255,.45)" stroke-width="1" stroke-linecap="round"/>
            <circle cx="15" cy="15" r="2.2" fill="#fff"/>
        </svg>`;
        document.querySelectorAll('.brand-mark').forEach(function (el) {
            el.innerHTML = svg;
            el.setAttribute('aria-label', 'Logo de TecnoRadar');
        });
    }

    function iniciarTituloDinamico() {
        aplicarLogoTecnoRadar();
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
