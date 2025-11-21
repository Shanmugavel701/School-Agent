document.getElementById('btn').addEventListener('click', fetchData);

async function fetchData() {
    const q = document.getElementById('q').value.trim();
    if (!q) { alert('Enter school name'); return; }

    const resDiv = document.getElementById('result');
    const downloadBtn = document.getElementById('downloadBtn');

    resDiv.style.display = 'block';
    resDiv.innerHTML = '<p>Loading…</p>';
    downloadBtn.style.display = "none";

    try {
        const resp = await fetch(`http://127.0.0.1:8000/api/school?q=${encodeURIComponent(q)}`);
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
            window.location.href = `http://127.0.0.1:8000/api/pdf?q=${encodeURIComponent(q)}`;
        };

    } catch (e) {
        resDiv.innerHTML = `<p>Error: ${e.message}</p>`;
    }
}
