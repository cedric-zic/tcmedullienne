// Initialize Map with Leaflet
function initMap() {
    const map = L.map('map').setView([45.024, -0.78], 11);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(map);

    // Markers for the two sites with precise GPS coordinates
    L.marker([45.032694, -0.791209]).addTo(map)
        .bindPopup("TC Médullienne - Castelnau de Médoc (33480)");
    L.marker([45.016582, -0.764977]).addTo(map)
        .bindPopup("TC Médullienne - Avensan (33480)");
}

// Carousel Logic (slides loaded from evenements.json)
let currentSlide = 0;
let totalSlides = 0;

function showSlide(index) {
    const carouselInner = document.getElementById('carouselInner');
    if (carouselInner) {
        carouselInner.style.transform = `translateX(-${index * 100}%)`;
    }
}

function nextSlide() {
    if (totalSlides === 0) return;
    currentSlide = (currentSlide + 1) % totalSlides;
    showSlide(currentSlide);
}

function prevSlide() {
    if (totalSlides === 0) return;
    currentSlide = (currentSlide - 1 + totalSlides) % totalSlides;
    showSlide(currentSlide);
}

async function chargerEvenements() {
    const carouselInner = document.getElementById('carouselInner');
    if (!carouselInner) return;

    let evenements = [];
    try {
        const reponse = await fetch('evenements.json', { cache: 'no-store' });
        if (reponse.ok) {
            const donnees = await reponse.json();
            if (Array.isArray(donnees)) evenements = donnees;
        }
    } catch (erreur) {
        console.warn('evenements.json indisponible :', erreur);
    }

    if (evenements.length === 0) return;

    carouselInner.innerHTML = '';
    for (const evenement of evenements) {
        const item = document.createElement('div');
        item.className = 'carousel-item';

        const image = document.createElement('img');
        image.src = evenement.image;
        image.alt = evenement.titre || 'Événement';

        const caption = document.createElement('div');
        caption.className = 'carousel-caption';
        caption.textContent = evenement.titre || '';

        item.appendChild(image);
        item.appendChild(caption);
        carouselInner.appendChild(item);
    }

    totalSlides = evenements.length;
    currentSlide = 0;
    showSlide(0);
    setInterval(nextSlide, 5000);
}

// Sponsor Rotation Logic (sponsors loaded from sponsors.json)
let sponsors = [];
let currentSponsorIndex = 0;
let sponsorTimer = null;

function showSponsor(index) {
    const sponsor = sponsors[index];
    const sponsorLink = document.getElementById('sponsorLink');
    const sponsorImage = document.getElementById('sponsorImage');

    if (sponsor && sponsorLink && sponsorImage) {
        sponsorLink.href = sponsor.url || '#';
        sponsorImage.src = sponsor.image;
        sponsorImage.alt = sponsor.nom || 'Sponsor';
    }
}

function nextSponsor() {
    if (sponsors.length === 0) return;
    currentSponsorIndex = (currentSponsorIndex + 1) % sponsors.length;
    showSponsor(currentSponsorIndex);
}

async function chargerSponsors() {
    const sponsorContainer = document.getElementById('sponsorContainer');
    if (!sponsorContainer) return;

    try {
        const reponse = await fetch('sponsors.json', { cache: 'no-store' });
        if (reponse.ok) {
            const donnees = await reponse.json();
            if (Array.isArray(donnees)) sponsors = donnees;
        }
    } catch (erreur) {
        console.warn('sponsors.json indisponible :', erreur);
    }

    if (sponsors.length === 0) {
        const section = sponsorContainer.closest('section.sponsors');
        if (section) section.style.display = 'none';
        return;
    }

    showSponsor(0);
    sponsorTimer = setInterval(nextSponsor, 3000);
}

// Mobile Menu Toggle
function toggleMenu() {
    const navLinks = document.querySelector('.nav-links');
    navLinks.classList.toggle('active'); // Bascule la classe 'active'
}

// Form Submission
document.addEventListener('DOMContentLoaded', function() {
    const contactForm = document.getElementById('contactForm');
    if (contactForm) {
        contactForm.addEventListener('submit', function(e) {
            e.preventDefault();
            alert('Message envoyé ! Nous vous répondrons bientôt.');
            this.reset();
        });
    }
});

// Form Email
document.addEventListener('DOMContentLoaded', function() {
    const email = 'contact' + String.fromCharCode(64) + 'tcmedullienne.fr';
    const emailLink = document.createElement('a');
    emailLink.href = 'mailto:' + email;
    emailLink.textContent = email;
    emailLink.classList.add('call-btn');
    const cible = document.getElementById('email-obfuscated');
    if (cible) cible.appendChild(emailLink);
});

// Load dynamic content
document.addEventListener('DOMContentLoaded', function() {
    chargerEvenements();
    chargerSponsors();
});
