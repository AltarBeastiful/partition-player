# Deployment on the main server

Target: the `main` host (Ubuntu 24.04, aarch64, 2 cores, 10 GB RAM), which already runs philou's
Caddy (`philou-web`) on ports 80/443 and PocketBase for pyrrhic. Every service there follows the
same pattern, and so does this one:

- the container joins the external Docker network `deploy_default`, publishes no port;
- its site block lives in `/home/ubuntu/caddy-sites/<name>.caddy`, which philou's Caddyfile
  imports; `docker exec philou-web caddy reload --config /etc/caddy/Caddyfile` applies it;
- the domain is `<name>.92.5.91.253.sslip.io`, so Caddy gets a Let's Encrypt certificate with no
  DNS work.

URL: <https://partition-player.92.5.91.253.sslip.io>

## Deploy

```
deploy/deploy.sh              # rsync, build on the server, start, install Caddy site, smoke test
deploy/deploy.sh --no-build   # restart only
```

The script ends with `free -m` and `docker stats` so the memory picture is in front of you.

## Resources

- Memory: homr peaks around 1.5 GB per page in the benchmark. The container is capped at 3 GB
  (`mem_limit`, swap disabled) and runs one job at a time, so the worst case leaves 7 GB to the
  rest of the host. Check with `docker stats partition-player` during a recognition.
- CPU: a recognition uses both cores for 15 s to a few minutes; `cpu_shares: 512` lets Caddy and
  PocketBase win contention.
- Disk: the image is about 1.5 GB (models included). A finished score keeps only
  `score.musicxml`, `thumb.jpg` and two small JSON files (about 50 KB); the input photo and the
  engine's intermediate files are deleted as soon as the job ends. Failed jobs keep their photo and
  logs for `PP_JOB_TTL_DAYS` (7) and are then removed. `PP_MAX_SCORES` (500) drops the oldest
  scores beyond that count. Old images are pruned on each deploy.

## Operations

```
ssh main
cd partition-player
docker compose -f deploy/compose.yaml logs -f --tail 100
docker compose -f deploy/compose.yaml restart
docker run --rm -v partition-player_data:/data alpine du -sh /data/jobs     # library size
docker run --rm -v partition-player_data:/data -v $PWD:/b alpine tar czf /b/pp-data.tgz -C /data .   # backup
```

There is no login. Anyone with the URL can add, rename and delete scores.
