import http from 'node:http';

const port = Number(process.env.PORT || 10000);
const host = '0.0.0.0';

const server = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, {'content-type':'application/json; charset=utf-8','cache-control':'no-store'});
    res.end(JSON.stringify({status:'ok',automatic_delivery:false,mode:'migration_staging',webhook_enabled:false}));
    return;
  }
  if (req.url === '/webhooks/tally') {
    res.writeHead(503, {'content-type':'application/json; charset=utf-8','cache-control':'no-store'});
    res.end(JSON.stringify({status:'disabled',reason:'migration_staging_not_connected'}));
    return;
  }
  res.writeHead(404, {'content-type':'application/json; charset=utf-8','cache-control':'no-store'});
  res.end(JSON.stringify({status:'not_found'}));
});

server.listen(port, host, () => {
  console.log(`migration staging listening on ${host}:${port}`);
});
