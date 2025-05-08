const net = require('net');
const puppeteer = require('puppeteer');

async function getAuctionTimer(domain, id_asta) {
    const url = `https://${domain}.bidoo.com/auction.php?a=${id_asta}`;
    const selector = `#DA${id_asta} > div.col-lg-5.col-md-5.col-sm-6.col-xs-12.action_auction > section.auction-action-container > div > div:nth-child(2) > section > div.auction-action-countdown > div > div`;

    let browser;
    try {
        browser = await puppeteer.launch({ headless: true });
        const page = await browser.newPage();
        await page.goto(url, { waitUntil: 'domcontentloaded' });
        await page.waitForSelector(selector);
        const timerText = await page.$eval(selector, element => element.textContent.trim());
        const timerValue = parseInt(timerText, 10);

        console.log(`Timer estratto da Node.js: ${timerValue}`);
        return timerValue;
    } catch (error) {
        console.error(`Errore durante l'estrazione del timer: ${error.message}`);
        return null;
    } finally {
        if (browser) {
            await browser.close();
        }
    }
}

function startSocketServer() {
    const server = net.createServer(async (socket) => {
        console.log("Client Python connesso");

        socket.on('data', async (data) => {
            const [domain, id_asta] = data.toString().split('|'); 
            console.log(`Parametri ricevuti da Python: domain=${domain}, id_asta=${id_asta}`);

            const timerNodeJS = await getAuctionTimer(domain, id_asta);
            if (timerNodeJS !== null) {
                socket.write(timerNodeJS.toString()); 
            }
        });

        socket.on('close', () => {
            console.log("Connessione chiusa");
        });

        socket.on('error', (err) => {
            console.error(`Errore durante la connessione: ${err.message}`);
        });
    });

    server.listen(65432, '127.0.0.1', () => {
        console.log("Socket server in ascolto su 127.0.0.1:65432");
    });
}

startSocketServer();