const puppeteer = require('puppeteer');

async function testRouting() {
  let browser;
  
  try {
    browser = await puppeteer.launch({
      headless: false,
      devtools: false,
      defaultViewport: { width: 1280, height: 720 }
    });
    
    const page = await browser.newPage();
    
    console.log('🔄 Loading app...');
    await page.goto('http://localhost:3000', { waitUntil: 'networkidle0' });
    
    // Take initial screenshot
    await page.screenshot({ path: 'routing-test-1-initial.png', fullPage: true });
    
    console.log('Current URL:', page.url());
    
    // Check if we can see navigation tabs
    const overviewTab = await page.$('a[href="/overview"]');
    const eventsTab = await page.$('a[href="/events"]');
    
    if (overviewTab && eventsTab) {
      console.log('✅ Navigation tabs found');
      
      // Test navigation
      console.log('🖱️  Clicking Events tab...');
      await eventsTab.click();
      await page.waitForTimeout(500);
      
      console.log('Current URL after Events click:', page.url());
      await page.screenshot({ path: 'routing-test-2-events.png', fullPage: true });
      
      // Test another tab
      console.log('🖱️  Clicking Overview tab...');
      await overviewTab.click();
      await page.waitForTimeout(500);
      
      console.log('Current URL after Overview click:', page.url());
      await page.screenshot({ path: 'routing-test-3-overview.png', fullPage: true });
      
      // Test browser back button
      console.log('⬅️  Testing browser back button...');
      await page.goBack();
      await page.waitForTimeout(500);
      
      console.log('Current URL after back:', page.url());
      await page.screenshot({ path: 'routing-test-4-back.png', fullPage: true });
      
      console.log('✅ Routing test completed successfully');
      
    } else {
      console.log('❌ Navigation tabs not found - might be login page');
      
      // Check for login elements
      const loginForm = await page.$('form, input[type="password"]');
      if (loginForm) {
        console.log('🔐 Login page detected');
        await page.screenshot({ path: 'routing-test-login.png', fullPage: true });
      }
    }
    
  } catch (error) {
    console.error('❌ Routing test failed:', error.message);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

testRouting();