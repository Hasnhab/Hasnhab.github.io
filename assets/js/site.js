const terminal = document.getElementById("terminal");

if (terminal) {
    const sequences = [
        [
            "[BOOT] Initializing security research environment...",
            "[OK] Loading analysis modules",
            "[OK] Attaching read-only traffic instrumentation",
            "[INFO] Data pipeline active",
            "[READY] Analyst control granted"
        ],
        [
            "[SCAN] Mapping application surface...",
            "[SCAN] Detecting API endpoints",
            "[SCAN] Analyzing authentication flows",
            "[INFO] Read-only mode (no modifications)",
            "[OK] Analysis complete"
        ],
        [
            "[STATS] Requests analyzed: 142",
            "[STATS] Endpoints mapped: 18",
            "[STATS] Authentication flows: 4",
            "[STATS] No anomalies detected",
            "[READY]"
        ]
    ];

    let sequenceIndex = 0;
    let lineIndex = 0;
    let charIndex = 0;
    let currentLine = "";
    let currentSequence = sequences[0];

    function cursor() {
        return '<span class="terminal-cursor" aria-hidden="true"></span>';
    }

    function typeWriter() {
        if (lineIndex < currentSequence.length) {
            if (charIndex < currentSequence[lineIndex].length) {
                currentLine += currentSequence[lineIndex].charAt(charIndex);
                terminal.innerHTML = currentLine + cursor();
                charIndex++;
                setTimeout(typeWriter, 28);
            } else {
                currentLine += "<br>";
                terminal.innerHTML = currentLine + cursor();
                lineIndex++;
                charIndex = 0;
                setTimeout(typeWriter, 650);
            }
        } else {
            setTimeout(nextSequence, 3200);
        }
    }

    function nextSequence() {
        sequenceIndex = (sequenceIndex + 1) % sequences.length;
        currentSequence = sequences[sequenceIndex];
        lineIndex = 0;
        charIndex = 0;
        currentLine = "";
        terminal.innerHTML = "";
        typeWriter();
    }

    typeWriter();
}

const hamburger = document.getElementById("hamburger");
const mobileMenu = document.getElementById("mobileMenu");

if (hamburger && mobileMenu) {
    hamburger.addEventListener("click", () => {
        mobileMenu.classList.toggle("active");
    });

    hamburger.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            mobileMenu.classList.toggle("active");
        }
    });

    document.querySelectorAll("#mobileMenu a").forEach(link => {
        link.addEventListener("click", () => {
            mobileMenu.classList.remove("active");
        });
    });
}