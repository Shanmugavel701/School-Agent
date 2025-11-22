document.getElementById('btn').addEventListener('click', fetchData);

// Automatically detect environment - use Render URL in production, empty string for localhost
const BACKEND_URL = window.location.hostname === 'school-agent-u680.onrender.com' 
    ? 'https://school-agent-u680.onrender.com' 
    : ''; // Empty string = relative URL (works for localhost)

async function fetchData() {
    const q = document.getElementById('q').value.trim();
    if (!q) { alert('Enter school name'); return; }

    const resDiv = document.getElementById('result');
    const downloadBtn = document.getElementById('downloadBtn');

    resDiv.style.display = 'block';
    resDiv.innerHTML = '<p>Loading…</p>';
    downloadBtn.style.display = "none";

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 120000); // 120 second timeout
        
        const resp = await fetch(`${BACKEND_URL}/api/school?q=${encodeURIComponent(q)}`, {
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        
        if (!resp.ok) {
            resDiv.innerHTML = `<p>Error: HTTP ${resp.status}</p>`;
            return;
        }
        
        const data = await resp.json();

        if (data.error) {
            resDiv.innerHTML = `<p>${data.error}</p>`;
            return;
        }

        let html = `<h2>${data.school_name || q}</h2>`;
        html += '<table>';

        const keys = [
            'address','location','contact','website','email','board',
            'classes_offered','fees','admission_process',
            'facilities','transport','rating','about','summary'
        ];

        for (const k of keys) {
            let v = data[k];
            if (Array.isArray(v)) v = v.join(', ');
            if (!v) v = '-';
            html += `<tr><th>${k.replace('_',' ').toUpperCase()}</th><td>${v}</td></tr>`;
        }

        html += '</table>';
        resDiv.innerHTML = html;

        // show download button
        downloadBtn.style.display = "inline-block";
        downloadBtn.onclick = () => {
            window.location.href = `${BACKEND_URL}/api/pdf?q=${encodeURIComponent(q)}`;
        };

    } catch (e) {
        console.error('Fetch error:', e);
        if (e.name === 'AbortError') {
            resDiv.innerHTML = `<p>Request timeout - server took too long to respond. Please try again.</p>`;
        } else {
            resDiv.innerHTML = `<p>Error: ${e.message}</p>`;
        }
    }
}
