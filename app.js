/* =========================================================
   REWIND // Y2K MAXIMALIST MUSIC ARCHIVE ENGINE (app.js)
   Features: Multi-Page Switching, Musician Showcase Motion, 3D Card Motion,
   Vinyl Ejection, Procedural Audio Synth & CD Burner Station
   (Bulletproof Bug-Free & Zero Exception Edition)
========================================================= */

const MUSICIAN_DATA = {
    daftpunk: {
        name: "DAFT PUNK",
        avatar: "🤖",
        era: "1999 FRENCH TOUCH",
        genre: "ELECTRONIC / HOUSE",
        bio: "Iconic French electronic music duo. Defined late 90s cyber-funk with groundbreaking robot helmets, vocoder vocals, and timeless Y2K synth riffs.",
        tracks: [
            { name: "▶ ONE MORE TIME (1999)", idx: 0 },
            { name: "▶ AROUND THE WORLD (1997)", idx: 1 },
            { name: "▶ HARDER, BETTER, FASTER (2001)", idx: 2 }
        ]
    },
    britney: {
        name: "BRITNEY SPEARS",
        avatar: "👑",
        era: "1999 TEEN POP ERA",
        genre: "Y2K DANCE POP",
        bio: "The undisputed Princess of Y2K Pop. Dominated MTV TRL charts, radio airwaves, and dance floors worldwide with iconic millennium hits.",
        tracks: [
            { name: "▶ ...BABY ONE MORE TIME (1998)", idx: 1 },
            { name: "▶ TOXIC (2003)", idx: 0 },
            { name: "▶ OOPS!... I DID IT AGAIN (2000)", idx: 2 }
        ]
    },
    prodigy: {
        name: "THE PRODIGY",
        avatar: "⚡",
        era: "1997 RAVE REVOLUTION",
        genre: "BIG BEAT / INDUSTRIAL",
        bio: "Pioneers of aggressive Y2K electronic rock and big beat rave anthems. Known for explosive energy, synth distortion, and futuristic visuals.",
        tracks: [
            { name: "▶ FIRESTARTER (1996)", idx: 2 },
            { name: "▶ BREATHE (1997)", idx: 0 },
            { name: "▶ SMACK MY BITCH UP (1997)", idx: 1 }
        ]
    },
    eiffel: {
        name: "EIFFEL 65",
        avatar: "🟦",
        era: "1998 EURODANCE",
        genre: "EURODANCE / ITALO-DANCE",
        bio: "Italian Eurodance group famous for global chart-topping synth-pop hit 'Blue (Da Ba Dee)' which defined the sound of 1999.",
        tracks: [
            { name: "▶ BLUE (DA BA DEE) (1998)", idx: 1 },
            { name: "▶ MOVE YOUR BODY (1999)", idx: 0 },
            { name: "▶ TOO MUCH OF HEAVEN (2000)", idx: 3 }
        ]
    },
    gorillaz: {
        name: "GORILLAZ",
        avatar: "🦍",
        era: "2001 VIRTUAL BAND",
        genre: "TRIP-HOP / ALTERNATIVE",
        bio: "World's first animated virtual band created by Damon Albarn and Jamie Hewlett. Fused Y2K hip-hop, dub, and alternative synth pop.",
        tracks: [
            { name: "▶ CLINT EASTWOOD (2001)", idx: 3 },
            { name: "▶ FEEL GOOD INC. (2005)", idx: 0 },
            { name: "▶ 19-2000 (2001)", idx: 2 }
        ]
    },
    outkast: {
        name: "OUTKAST",
        avatar: "🔥",
        era: "2000 STANKONIA",
        genre: "FUNK RAP / HIP-HOP",
        bio: "Atlanta rap duo Andre 3000 & Big Boi who redefined Y2K hip-hop with eclectic funk, hyper-speed flows, and futuristic production.",
        tracks: [
            { name: "▶ B.O.B. (BOMBS OVER BAGHDAD) (2000)", idx: 0 },
            { name: "▶ MS. JACKSON (2000)", idx: 1 },
            { name: "▶ HEY YA! (2003)", idx: 2 }
        ]
    }
};

let currentArtistKey = 'daftpunk';

document.addEventListener('DOMContentLoaded', () => {
    console.log("⚡ REWIND // Y2K Multi-Page Audio Engine Initializing...");

    initNavigation();
    initThreeJS();
    initAudioSynth();
    initDraggableWindows();
    initStickerBomber();
    initChatroom();
    initCard3DTilt();
    initMusicianShowcase();
    initCDBurner();
    initControls();
});

/* =========================================================
   1. MULTI-PAGE NAVIGATION SYSTEM
========================================================= */
function initNavigation() {
    const navLinks = document.querySelectorAll('.nav-link');
    const pageViews = document.querySelectorAll('.page-view');

    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            const targetPage = link.getAttribute('data-page');
            if (!targetPage) return;

            navLinks.forEach(l => l.classList.remove('active'));
            link.classList.add('active');

            pageViews.forEach(page => {
                page.classList.remove('active');
                if (page.id === `page-${targetPage}`) {
                    page.classList.add('active');
                }
            });

            triggerSFX('beep');
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    });
}

/* =========================================================
   2. THREE.JS 3D WEBGL ENGINE
========================================================= */
let scene, camera, renderer, cdMesh, particleGroup, crystalGroup;
let mouseX = 0, mouseY = 0;

function initThreeJS() {
    const canvas = document.getElementById('three-canvas');
    if (!canvas || typeof THREE === 'undefined') return;

    const width = canvas.clientWidth || window.innerWidth || 800;
    const height = canvas.clientHeight || window.innerHeight || 600;

    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.z = 15;

    renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.85);
    scene.add(ambientLight);

    const pinkLight = new THREE.PointLight(0xff00cc, 4, 35);
    pinkLight.position.set(10, 10, 10);
    scene.add(pinkLight);

    const cyanLight = new THREE.PointLight(0x00eaff, 4, 35);
    cyanLight.position.set(-10, -10, 10);
    scene.add(cyanLight);

    create3DCD();
    createParticleCloud();
    createCyberCrystals();

    window.addEventListener('mousemove', (e) => {
        mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
        mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
    });

    window.addEventListener('resize', () => {
        const newW = window.innerWidth || 800;
        const newH = window.innerHeight || 600;
        camera.aspect = newW / newH;
        camera.updateProjectionMatrix();
        renderer.setSize(newW, newH);
    });

    animateThree();
}

function create3DCD() {
    const geometry = new THREE.CylinderGeometry(3.6, 3.6, 0.12, 64);

    const texCanvas = document.createElement('canvas');
    texCanvas.width = 512;
    texCanvas.height = 512;
    const ctx = texCanvas.getContext('2d');

    const grad = ctx.createConicGradient(0, 256, 256);
    grad.addColorStop(0, '#ff00cc');
    grad.addColorStop(0.25, '#00eaff');
    grad.addColorStop(0.5, '#ffff00');
    grad.addColorStop(0.75, '#8b5cff');
    grad.addColorStop(1, '#ff00cc');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 512, 512);

    ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
    ctx.lineWidth = 2;
    for (let r = 50; r < 240; r += 7) {
        ctx.beginPath();
        ctx.arc(256, 256, r, 0, Math.PI * 2);
        ctx.stroke();
    }

    ctx.fillStyle = '#12001f';
    ctx.beginPath();
    ctx.arc(256, 256, 45, 0, Math.PI * 2);
    ctx.fill();

    const texture = new THREE.CanvasTexture(texCanvas);

    const material = new THREE.MeshStandardMaterial({
        map: texture,
        metalness: 0.95,
        roughness: 0.05,
        side: THREE.DoubleSide
    });

    cdMesh = new THREE.Mesh(geometry, material);
    cdMesh.rotation.x = Math.PI / 3;
    cdMesh.rotation.z = Math.PI / 6;
    cdMesh.position.set(4, 0, -2);
    scene.add(cdMesh);
}

function createParticleCloud() {
    particleGroup = new THREE.Group();
    const particleCount = 140;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const colors = Float32Array.from(Array(particleCount * 3).fill(0).map(() => Math.random()));

    for (let i = 0; i < particleCount * 3; i += 3) {
        positions[i] = (Math.random() - 0.5) * 45;
        positions[i + 1] = (Math.random() - 0.5) * 45;
        positions[i + 2] = (Math.random() - 0.5) * 25;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({
        size: 0.35,
        vertexColors: true,
        transparent: true,
        opacity: 0.85
    });

    const particles = new THREE.Points(geometry, material);
    particleGroup.add(particles);
    scene.add(particleGroup);
}

function createCyberCrystals() {
    crystalGroup = new THREE.Group();
    const geom = new THREE.OctahedronGeometry(0.7, 0);

    for (let i = 0; i < 10; i++) {
        const mat = new THREE.MeshStandardMaterial({
            color: (i % 2 === 0) ? 0x00eaff : 0xff00cc,
            wireframe: true
        });
        const crystal = new THREE.Mesh(geom, mat);
        crystal.position.set(
            (Math.random() - 0.5) * 22,
            (Math.random() - 0.5) * 18,
            (Math.random() - 0.5) * 12
        );
        crystalGroup.add(crystal);
    }
    scene.add(crystalGroup);
}

function animateThree() {
    requestAnimationFrame(animateThree);

    if (cdMesh) {
        cdMesh.rotation.z += 0.015;
        cdMesh.rotation.y = mouseX * 0.3;
        cdMesh.rotation.x = Math.PI / 3 + mouseY * 0.2;
    }

    if (particleGroup) {
        particleGroup.rotation.y += 0.002;
    }

    if (crystalGroup) {
        crystalGroup.children.forEach((c, idx) => {
            c.rotation.x += 0.02 * (idx % 2 === 0 ? 1 : -1);
            c.rotation.y += 0.02;
        });
    }

    camera.position.x += (mouseX * 2.5 - camera.position.x) * 0.05;
    camera.position.y += (-mouseY * 2.5 - camera.position.y) * 0.05;

    renderer.render(scene, camera);
}

/* =========================================================
   3. MUSICIAN SHOWCASE & ANIMATED MUSICIAN SWITCHER
========================================================= */
function initMusicianShowcase() {
    const tabs = document.querySelectorAll('.musician-tab');
    const stageCard = document.getElementById('artist-stage-card');
    const vinylDisc = document.getElementById('artist-vinyl');
    const nextBtn = document.getElementById('btn-next-musician');
    const playArtistSynthBtn = document.getElementById('btn-play-artist-synth');

    const artistKeys = Object.keys(MUSICIAN_DATA);

    const switchArtist = (artistKey) => {
        if (!MUSICIAN_DATA[artistKey]) return;
        currentArtistKey = artistKey;

        // Card Motion & Tape Eject
        if (stageCard) stageCard.classList.add('switch-anim');
        if (vinylDisc) vinylDisc.classList.add('eject-spin');
        triggerSFX('scratch');

        setTimeout(() => {
            const data = MUSICIAN_DATA[artistKey];
            const nameEl = document.getElementById('artist-name');
            const emojiEl = document.getElementById('artist-emoji');
            const eraEl = document.getElementById('artist-era');
            const genreEl = document.getElementById('artist-genre');
            const bioEl = document.getElementById('artist-bio');

            if (nameEl) nameEl.textContent = data.name;
            if (emojiEl) emojiEl.textContent = data.avatar;
            if (eraEl) eraEl.textContent = data.era;
            if (genreEl) genreEl.textContent = data.genre;
            if (bioEl) bioEl.textContent = data.bio;

            const tracksUl = document.getElementById('artist-tracks');
            if (tracksUl) {
                tracksUl.innerHTML = '';
                data.tracks.forEach(tr => {
                    const li = document.createElement('li');
                    li.innerHTML = `<button class="hit-play-btn" data-track="${tr.idx}">${tr.name}</button>`;
                    tracksUl.appendChild(li);
                });

                tracksUl.querySelectorAll('.hit-play-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const idx = parseInt(btn.getAttribute('data-track') || '0');
                        changeTrack(idx);
                        playTrack();
                        triggerSFX('laser');
                    });
                });
            }

            if (stageCard) stageCard.classList.remove('switch-anim');
            setTimeout(() => {
                if (vinylDisc) vinylDisc.classList.remove('eject-spin');
            }, 300);
        }, 200);
    };

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const key = tab.getAttribute('data-artist');
            switchArtist(key);
        });
    });

    if (nextBtn) {
        nextBtn.addEventListener('click', () => {
            const currentIdx = artistKeys.indexOf(currentArtistKey);
            const nextIdx = (currentIdx + 1) % artistKeys.length;
            const nextKey = artistKeys[nextIdx];
            
            tabs.forEach(t => {
                t.classList.toggle('active', t.getAttribute('data-artist') === nextKey);
            });
            switchArtist(nextKey);
        });
    }

    if (playArtistSynthBtn) {
        playArtistSynthBtn.addEventListener('click', () => {
            playTrack();
            triggerSFX('arp');
        });
    }
}

/* =========================================================
   4. CD BURNER STATION LOGIC
========================================================= */
function initCDBurner() {
    const input = document.getElementById('cd-label-input');
    const titleText = document.getElementById('cd-title-text');
    const burnBtn = document.getElementById('btn-burn-cd');
    const statusBox = document.getElementById('burn-status-box');
    const percentText = document.getElementById('burn-percent');
    const fillBar = document.getElementById('burn-fill-bar');

    if (input && titleText) {
        input.addEventListener('input', (e) => {
            titleText.textContent = e.target.value || "Y2K MIXTAPE 2000";
        });
    }

    if (burnBtn && statusBox) {
        burnBtn.addEventListener('click', () => {
            statusBox.style.display = 'block';
            triggerSFX('laser');
            let pct = 0;

            const burnInterval = setInterval(() => {
                pct += 10;
                if (percentText) percentText.textContent = `BURNING CD-R... ${pct}%`;
                if (fillBar) fillBar.style.width = `${pct}%`;

                if (pct >= 100) {
                    clearInterval(burnInterval);
                    if (percentText) percentText.textContent = `⚡ CD-R MIXTAPE BURN SUCCESSFUL!`;
                    triggerSFX('explosion');
                    alert("CD-R Mixtape successfully burned! Ready for playback on Rewind Sound Deck!");
                }
            }, 300);
        });
    }
}

/* =========================================================
   5. WEB AUDIO SYNTH & REWIND ENGINE
========================================================= */
let audioCtx, analyser, gainNode, isPlaying = false;
let currentTrackIndex = 0;
let trackTimerInterval = null;
let currentTrackSeconds = 0;
let synthLoopId = null;

const trackList = [
    { title: "CYBER SYNTH 1999", bpm: 138, genre: "90s EURO-BEAT", duration: "02:45", durationSec: 165 },
    { title: "EURODANCE PULSE '99", bpm: 142, genre: "DANCE REVOLUTION", duration: "03:12", durationSec: 192 },
    { title: "ACID BASS 2000", bpm: 130, genre: "ACID TECHNO", duration: "02:30", durationSec: 150 },
    { title: "VAPORWAVE DREAM MATRIX", bpm: 110, genre: "CHIPTUNE DREAMS", duration: "04:05", durationSec: 245 }
];

function initAudioSynth() {
    const setupAudio = () => {
        if (!audioCtx) {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            audioCtx = new AudioContext();
            analyser = audioCtx.createAnalyser();
            analyser.fftSize = 64;

            gainNode = audioCtx.createGain();
            gainNode.gain.value = 0.8;
            gainNode.connect(analyser);
            analyser.connect(audioCtx.destination);

            drawVisualizer();
        }
    };

    document.body.addEventListener('click', setupAudio, { once: true });

    const playBtn = document.getElementById('wa-play');
    const pauseBtn = document.getElementById('wa-pause');
    const stopBtn = document.getElementById('wa-stop');
    const rewindBtn = document.getElementById('wa-rewind');
    const nextBtn = document.getElementById('wa-next');

    if (playBtn) playBtn.addEventListener('click', () => { setupAudio(); togglePlayPause(); });
    if (pauseBtn) pauseBtn.addEventListener('click', pauseTrack);
    if (stopBtn) stopBtn.addEventListener('click', stopTrack);
    
    if (rewindBtn) {
        rewindBtn.addEventListener('click', () => {
            setupAudio();
            triggerSFX('scratch');
            currentTrackSeconds = 0;
            updateTimerDisplay();
        });
    }

    if (nextBtn) nextBtn.addEventListener('click', () => changeTrack((currentTrackIndex + 1) % trackList.length));

    document.querySelectorAll('#playlist-list li').forEach(li => {
        li.addEventListener('click', () => {
            const idx = parseInt(li.getAttribute('data-index') || '0');
            setupAudio();
            changeTrack(idx);
            playTrack();
        });
    });

    const volSlider = document.getElementById('wa-volume');
    if (volSlider) {
        volSlider.addEventListener('input', (e) => {
            if (gainNode) gainNode.gain.value = e.target.value / 100;
        });
    }

    const heroEnterBtn = document.getElementById('btn-enter-archive');
    if (heroEnterBtn) {
        heroEnterBtn.addEventListener('click', () => {
            setupAudio();
            playTrack();
            document.getElementById('window-winamp')?.scrollIntoView({ behavior: 'smooth' });
        });
    }

    const heroRewindBtn = document.getElementById('btn-rewind-sfx');
    if (heroRewindBtn) {
        heroRewindBtn.addEventListener('click', () => {
            setupAudio();
            triggerSFX('scratch');
            currentTrackSeconds = 0;
            updateTimerDisplay();
        });
    }

    document.querySelectorAll('.album-card').forEach(card => {
        card.addEventListener('click', () => {
            const trackIdx = parseInt(card.getAttribute('data-track') || '0');
            setupAudio();
            changeTrack(trackIdx);
            playTrack();
            triggerSFX('laser');
        });
    });
}

function togglePlayPause() {
    if (isPlaying) {
        pauseTrack();
    } else {
        playTrack();
    }
}

function playTrack() {
    if (!audioCtx) return;
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
    isPlaying = true;
    startProceduralAudio();
    startTimer();
    updateLCDDisplay();

    const playBtn = document.getElementById('wa-play');
    if (playBtn) playBtn.innerHTML = `<i class="fa-solid fa-pause"></i> PAUSE`;
}

function pauseTrack() {
    isPlaying = false;
    stopTimer();
    if (synthLoopId) clearInterval(synthLoopId);

    const playBtn = document.getElementById('wa-play');
    if (playBtn) playBtn.innerHTML = `<i class="fa-solid fa-play"></i> PLAY`;
}

function stopTrack() {
    isPlaying = false;
    stopTimer();
    currentTrackSeconds = 0;
    updateTimerDisplay();
    if (synthLoopId) clearInterval(synthLoopId);

    const playBtn = document.getElementById('wa-play');
    if (playBtn) playBtn.innerHTML = `<i class="fa-solid fa-play"></i> PLAY`;
}

function changeTrack(index) {
    currentTrackIndex = index;
    currentTrackSeconds = 0;

    document.querySelectorAll('#playlist-list li').forEach((li, idx) => {
        li.classList.toggle('active', idx === currentTrackIndex);
    });

    updateLCDDisplay();
    if (isPlaying) {
        playTrack();
    }
}

function updateLCDDisplay() {
    const track = trackList[currentTrackIndex];
    const nameEl = document.getElementById('lcd-track-name');
    const heroTitleEl = document.getElementById('hero-track-title');

    if (nameEl) nameEl.textContent = `${currentTrackIndex + 1}. ${track.title}`;
    if (heroTitleEl) heroTitleEl.textContent = track.title;
}

function startTimer() {
    stopTimer();
    trackTimerInterval = setInterval(() => {
        currentTrackSeconds++;
        updateTimerDisplay();
    }, 1000);
}

function stopTimer() {
    if (trackTimerInterval) clearInterval(trackTimerInterval);
}

function updateTimerDisplay() {
    const timeEl = document.getElementById('audio-time');
    const fillEl = document.getElementById('track-progress-fill');
    const track = trackList[currentTrackIndex];

    if (timeEl) {
        const mins = String(Math.floor(currentTrackSeconds / 60)).padStart(2, '0');
        const secs = String(currentTrackSeconds % 60).padStart(2, '0');
        timeEl.textContent = `${mins}:${secs}`;
    }

    if (fillEl && track) {
        const pct = Math.min(100, (currentTrackSeconds / track.durationSec) * 100);
        fillEl.style.width = `${pct}%`;
    }
}

function startProceduralAudio() {
    if (synthLoopId) clearInterval(synthLoopId);
    if (!audioCtx) return;

    const track = trackList[currentTrackIndex];
    const bpm = track.bpm;
    const stepTime = (60 / bpm) * 1000 / 4;

    let step = 0;
    const scale = [220, 261.63, 293.66, 329.63, 392.00, 440.00, 523.25];

    synthLoopId = setInterval(() => {
        if (!isPlaying || !audioCtx) return;

        const now = audioCtx.currentTime;

        if (step % 4 === 0) {
            const kickOsc = audioCtx.createOscillator();
            const kickGain = audioCtx.createGain();
            kickOsc.frequency.setValueAtTime(160, now);
            kickOsc.frequency.exponentialRampToValueAtTime(0.01, now + 0.15);
            kickGain.gain.setValueAtTime(1.0, now);
            kickGain.gain.exponentialRampToValueAtTime(0.01, now + 0.15);
            kickOsc.connect(kickGain);
            kickGain.connect(gainNode);
            kickOsc.start(now);
            kickOsc.stop(now + 0.15);
        }

        if (step % 2 === 0) {
            const bassOsc = audioCtx.createOscillator();
            const bassGain = audioCtx.createGain();
            const noteIndex = (step / 2) % scale.length;
            bassOsc.type = (currentTrackIndex === 2) ? 'sawtooth' : 'square';
            bassOsc.frequency.setValueAtTime(scale[noteIndex] / 2, now);

            bassGain.gain.setValueAtTime(0.35, now);
            bassGain.gain.exponentialRampToValueAtTime(0.01, now + 0.14);

            bassOsc.connect(bassGain);
            bassGain.connect(gainNode);
            bassOsc.start(now);
            bassOsc.stop(now + 0.14);
        }

        if (step % 1 === 0) {
            const leadOsc = audioCtx.createOscillator();
            const leadGain = audioCtx.createGain();
            const leadFreq = scale[(step * 3) % scale.length] * (currentTrackIndex % 2 === 0 ? 2 : 1.5);
            leadOsc.type = 'triangle';
            leadOsc.frequency.setValueAtTime(leadFreq, now);

            leadGain.gain.setValueAtTime(0.18, now);
            leadGain.gain.exponentialRampToValueAtTime(0.001, now + 0.09);

            leadOsc.connect(leadGain);
            leadGain.connect(gainNode);
            leadOsc.start(now);
            leadOsc.stop(now + 0.09);
        }

        step = (step + 1) % 16;
    }, stepTime);
}

/* =========================================================
   6. CANVAS FREQUENCY VISUALIZER
========================================================= */
function drawVisualizer() {
    const canvas = document.getElementById('audio-visualizer');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const bufferLength = analyser ? analyser.frequencyBinCount : 32;
    const dataArray = new Uint8Array(bufferLength);

    function renderFrame() {
        requestAnimationFrame(renderFrame);

        ctx.fillStyle = '#000000';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        if (analyser && isPlaying) {
            analyser.getByteFrequencyData(dataArray);
        } else {
            for (let i = 0; i < bufferLength; i++) {
                dataArray[i] = Math.sin(Date.now() * 0.006 + i * 0.4) * 20 + 20;
            }
        }

        const barWidth = (canvas.width / bufferLength) * 2.2;
        let x = 0;

        for (let i = 0; i < bufferLength; i++) {
            const barHeight = (dataArray[i] / 255) * canvas.height * 0.9;

            const grad = ctx.createLinearGradient(0, canvas.height, 0, 0);
            grad.addColorStop(0, '#ff00cc');
            grad.addColorStop(0.5, '#00eaff');
            grad.addColorStop(1, '#ffff00');

            ctx.fillStyle = grad;
            ctx.fillRect(x, canvas.height - barHeight, barWidth - 2, barHeight);

            x += barWidth;
        }
    }

    renderFrame();
}

/* =========================================================
   7. PROCEDURAL SOUND EFFECTS (SFX)
========================================================= */
function triggerSFX(type) {
    if (!audioCtx) {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        audioCtx = new AudioContext();
    }
    if (audioCtx.state === 'suspended') audioCtx.resume();

    const now = audioCtx.currentTime;

    if (type === 'modem') {
        const osc = audioCtx.createOscillator();
        const g = audioCtx.createGain();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(1200, now);
        osc.frequency.setValueAtTime(2400, now + 0.1);
        osc.frequency.setValueAtTime(600, now + 0.25);
        osc.frequency.setValueAtTime(1800, now + 0.4);
        g.gain.setValueAtTime(0.3, now);
        g.gain.exponentialRampToValueAtTime(0.01, now + 0.6);
        osc.connect(g);
        g.connect(audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.6);
    } else if (type === 'laser') {
        const osc = audioCtx.createOscillator();
        const g = audioCtx.createGain();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(1600, now);
        osc.frequency.exponentialRampToValueAtTime(100, now + 0.2);
        g.gain.setValueAtTime(0.4, now);
        g.gain.exponentialRampToValueAtTime(0.01, now + 0.2);
        osc.connect(g);
        g.connect(audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.2);
    } else if (type === 'beep') {
        const osc = audioCtx.createOscillator();
        const g = audioCtx.createGain();
        osc.type = 'square';
        osc.frequency.setValueAtTime(880, now);
        g.gain.setValueAtTime(0.3, now);
        g.gain.exponentialRampToValueAtTime(0.01, now + 0.15);
        osc.connect(g);
        g.connect(audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.15);
    } else if (type === 'scratch') {
        const osc = audioCtx.createOscillator();
        const g = audioCtx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(350, now);
        osc.frequency.linearRampToValueAtTime(1400, now + 0.1);
        osc.frequency.linearRampToValueAtTime(250, now + 0.2);
        g.gain.setValueAtTime(0.4, now);
        g.gain.exponentialRampToValueAtTime(0.01, now + 0.2);
        osc.connect(g);
        g.connect(audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.2);
    } else if (type === 'arp') {
        [440, 554.37, 659.25, 880].forEach((freq, idx) => {
            const osc = audioCtx.createOscillator();
            const g = audioCtx.createGain();
            osc.frequency.setValueAtTime(freq, now + idx * 0.05);
            g.gain.setValueAtTime(0.2, now + idx * 0.05);
            g.gain.exponentialRampToValueAtTime(0.01, now + idx * 0.05 + 0.1);
            osc.connect(g);
            g.connect(audioCtx.destination);
            osc.start(now + idx * 0.05);
            osc.stop(now + idx * 0.05 + 0.1);
        });
    } else if (type === 'explosion') {
        const bufferSize = audioCtx.sampleRate * 0.3;
        const buffer = audioCtx.createBuffer(1, bufferSize, audioCtx.sampleRate);
        const output = buffer.getChannelData(0);
        for (let i = 0; i < bufferSize; i++) {
            output[i] = Math.random() * 2 - 1;
        }
        const whiteNoise = audioCtx.createBufferSource();
        whiteNoise.buffer = buffer;
        const g = audioCtx.createGain();
        g.gain.setValueAtTime(0.5, now);
        g.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
        whiteNoise.connect(g);
        g.connect(audioCtx.destination);
        whiteNoise.start(now);
    }
}

/* =========================================================
   8. DRAGGABLE WINDOWS ENGINE
========================================================= */
let topZIndex = 100;

function initDraggableWindows() {
    const windows = document.querySelectorAll('.y2k-window');

    windows.forEach(win => {
        const titlebar = win.querySelector('.window-titlebar');

        win.addEventListener('mousedown', () => {
            topZIndex++;
            win.style.zIndex = topZIndex;
        });

        if (titlebar) {
            let isDragging = false;
            let offsetX = 0, offsetY = 0;

            titlebar.addEventListener('mousedown', (e) => {
                isDragging = true;
                const rect = win.getBoundingClientRect();
                offsetX = e.clientX - rect.left;
                offsetY = e.clientY - rect.top;
            });

            document.addEventListener('mousemove', (e) => {
                if (!isDragging) return;
                win.style.left = `${e.clientX - offsetX}px`;
                win.style.top = `${e.clientY - offsetY}px`;
            });

            document.addEventListener('mouseup', () => {
                isDragging = false;
            });
        }

        const closeBtn = win.querySelector('.win-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                win.style.display = 'none';
                triggerSFX('beep');
            });
        }
    });
}

/* =========================================================
   9. STICKER BOMBING ENGINE
========================================================= */
let stickerMode = false;
const stickerEmojis = ['📼', '💿', '✦', '👾', '⚡', '🌐', '💖', '🎧', '🛸', '★', '🔥', '🔮', '🦋'];

function initStickerBomber() {
    const container = document.getElementById('sticker-container');
    const toggleBtn = document.getElementById('toggle-sticker-mode');
    const heroBtn = document.getElementById('btn-sticker-bomb');

    const toggle = () => {
        stickerMode = !stickerMode;
        if (toggleBtn) toggleBtn.classList.toggle('active', stickerMode);
        document.body.style.cursor = stickerMode ? 'copy' : 'crosshair';
    };

    if (toggleBtn) toggleBtn.addEventListener('click', toggle);
    if (heroBtn) heroBtn.addEventListener('click', toggle);

    document.addEventListener('click', (e) => {
        if (!stickerMode) return;
        if (e.target.closest('.nav-btn') || e.target.closest('.win-btn') || e.target.closest('button')) return;

        const sticker = document.createElement('div');
        sticker.className = 'sticker-item';
        sticker.textContent = stickerEmojis[Math.floor(Math.random() * stickerEmojis.length)];
        const rot = (Math.random() - 0.5) * 60;
        sticker.style.setProperty('--rot', `${rot}deg`);
        sticker.style.left = `${e.clientX - 20}px`;
        sticker.style.top = `${e.clientY - 20}px`;

        sticker.addEventListener('click', (stkEvt) => {
            stkEvt.stopPropagation();
            sticker.remove();
            triggerSFX('beep');
        });

        container?.appendChild(sticker);
        triggerSFX('scratch');
    });
}

/* =========================================================
   10. CHATROOM SIMULATOR
========================================================= */
function initChatroom() {
    const form = document.getElementById('chat-form');
    const input = document.getElementById('chat-input');
    const messages = document.getElementById('chat-messages');

    if (!form || !input || !messages) return;

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;

        addMessage('You', text, 'user');
        input.value = '';
        triggerSFX('beep');

        setTimeout(() => {
            const botReplies = [
                "REWIND 2000 audio deck is playing classic heat 🔥",
                "Hit the REWIND button for tape rewind sound effects! 📼",
                "Y2K Maximalism aesthetic is 100% spot on! 🚀",
                "Sticker bomb mode makes the layout super fun ✨",
                "Web Audio synth engine sounds awesome!"
            ];
            const reply = botReplies[Math.floor(Math.random() * botReplies.length)];
            addMessage('CyberBot_2000', reply, 'sys');
        }, 1200);
    });

    function addMessage(user, msg, typeClass) {
        const div = document.createElement('div');
        div.className = 'chat-msg';
        div.innerHTML = `<span class="user ${typeClass}">${user}:</span> ${msg}`;
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    }
}

/* =========================================================
   11. 3D CARD TILT EFFECT
========================================================= */
function initCard3DTilt() {
    const cards = document.querySelectorAll('.album-card');

    cards.forEach(card => {
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            const rotateX = (y - rect.height / 2) / 12;
            const rotateY = (x - rect.width / 2) / -12;

            card.style.transform = `perspective(800px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-8px)`;
        });

        card.addEventListener('mouseleave', () => {
            card.style.transform = '';
        });
    });
}

function initControls() {
    document.getElementById('sfx-modem')?.addEventListener('click', () => triggerSFX('modem'));
    document.getElementById('sfx-laser')?.addEventListener('click', () => triggerSFX('laser'));
    document.getElementById('sfx-scratch')?.addEventListener('click', () => triggerSFX('scratch'));
    document.getElementById('sfx-beep')?.addEventListener('click', () => triggerSFX('beep'));
    document.getElementById('sfx-arp')?.addEventListener('click', () => triggerSFX('arp'));
    document.getElementById('sfx-explosion')?.addEventListener('click', () => triggerSFX('explosion'));
    document.getElementById('logo-trigger')?.addEventListener('click', () => triggerSFX('scratch'));
}
