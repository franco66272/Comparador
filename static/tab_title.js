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

    function iniciarTituloDinamico() {
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
