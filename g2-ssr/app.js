const http = require('http');
const url = require("url");
const util = require('util');
const { createChart } = require('@antv/g2-ssr');
const port = 3000;

http.createServer((req, res) => {
    res.statusCode = 200,
        res.setHeader('Content-Type', 'text/plain;charset=utf-8');
    if (req.method === 'GET') {
        toGet(req, res);
    } else if (req.method === 'POST') {
        toPost(req, res);
    }
}).listen(port, () => {
    console.log(`Server listening on: http://localhost:${port}`);
});

// 创建 Chart 和配置
async function GenerateCharts(obj) {
    const options = JSON.parse(obj.options || "{}") || {
        width: 640,
        height: 480,
        imageType: 'png', // or 'jpeg'
        // 其他的配置透传 G2 Spec，可以参考 G2 的配置文档
        type: 'interval',
        data: [
            { genre: ' UIUI看看', sold: 278 },
            { genre: 'Strategy', sold: 115 },
            { genre: 'Action', sold: 120 },
            { genre: 'Shooter', sold: 350 },
            { genre: 'Other', sold: 150 },
        ],
        encode: {
            x: 'genre',
            y: 'sold',
            color: 'genre',
        },
    }
    const chart = await createChart(options);

    // 导出
    chart.exportToFile(obj.id || 'chart');
    // -> chart.png

    chart.toBuffer();
}
// -> get buffer


//获取GET请求内容 
function toGet(req, res) {
    let data = 'GET请求内容：\n' + util.inspect(url.parse(req.url));
    res.end(data);
    console.log(data);
}

//获取POST请求内容、cookie 
function toPost(req, res) {
    req.on('data', function (chunk) {
        GenerateCharts(JSON.parse(chunk))
        res.end('complete');
    });
}