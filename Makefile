up:
\tdocker compose up --build -d || docker-compose up --build -d
down:
\tdocker compose down || docker-compose down
logs:
\tdocker compose logs -f || docker-compose logs -f
rebuild:
\tdocker compose build --no-cache || docker-compose build --no-cache
