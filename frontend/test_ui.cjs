const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage();
  
  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('requestfailed', request => {
    console.log(`REQUEST FAILED: ${request.url()} - ${request.failure()?.errorText || 'Unknown error'}`);
  });

  await page.goto('http://localhost:5173');
  
  // Login
  await page.type('#email', 'center@test.com');
  await page.type('#password', 'pass');
  await page.click('button[type="submit"]');
  
  await page.waitForTimeout(2000);
  
  // Enter Paper ID and Session ID
  await page.type('#paper-id', '20');
  await page.type('#session-id', '20');
  
  console.log("Clicking Download...");
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const dlBtn = btns.find(b => b.textContent.includes('Download Watermarked Paper'));
    if (dlBtn) dlBtn.click();
  });
  
  await page.waitForTimeout(3000);
  
  // Check the message
  const msg = await page.evaluate(() => {
    const err = document.querySelector('.error-message');
    if (err) return err.innerText;
    const succ = document.querySelector('.success-message');
    if (succ) return succ.innerText;
    return "No message found.";
  });
  console.log("Result message:", msg);
  
  await browser.close();
})();
