/**
 * Frontend app copied into frontend/ so it can be served as static files.
 * (Original file remains at project root.)
 */

// Minimal wrapper to import the original script file if present
(async function(){
  try{
    // if a sibling app.js exists in the root, prefer that for easier editing
    const rootScript = '../app.js';
    const res = await fetch(rootScript);
    if (res.ok) {
      const code = await res.text();
      const blob = new Blob([code], { type: 'text/javascript' });
      const url = URL.createObjectURL(blob);
      const s = document.createElement('script'); s.src = url; document.body.appendChild(s);
      return;
    }
  }catch(e){}
  // fallback: small inline no-op
  console.warn('Could not load root/app.js; frontend functionality may be limited.');
})();
