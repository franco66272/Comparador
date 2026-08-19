# TecnoRadar — publicación en Internet

## Arquitectura
- `web`: Flask servido con Gunicorn.
- `verifier`: verificación continua de precios.
- `caddy`: HTTPS automático y proxy inverso.

## Requisitos
VPS Linux con Docker y Docker Compose.

## Primer despliegue
1. Copiar el proyecto al VPS.
2. Crear `.env` a partir de `.env.example` y colocar el dominio real.
3. Crear los servicios:
   `docker compose -f docker-compose.public.yml --env-file .env up -d --build`
4. Caddy solicitará el certificado HTTPS automáticamente cuando el dominio apunte al VPS.

## DNS
Crear un registro A del dominio apuntando a la IP pública del VPS.
Si se usa también `www`, agregar otro registro o redirección.

## Verificación
- Web: `docker compose -f docker-compose.public.yml logs -f web`
- Precios: `docker compose -f docker-compose.public.yml logs -f verifier`
- Caddy: `docker compose -f docker-compose.public.yml logs -f caddy`

## Persistencia
Los JSON del catálogo están en el directorio del proyecto y se montan directamente en ambos servicios. Antes de actualizaciones grandes, realizar una copia de seguridad del directorio completo.

## Nota de producción
El servidor público utiliza Gunicorn; `app.run()` queda solo para desarrollo local. El verificador corre separado para no bloquear las peticiones web.
