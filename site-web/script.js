// Initialize Map with Leaflet
function initMap() {
    const map = L.map('map').setView([45.024, -0.78], 11);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(map);

    // Markers for the two sites with precise GPS coordinates
    L.marker([45.032694, -0.791209]).addTo(map)
        .bindPopup("TC Médullienne - Castelnau de Médoc (33480)");
    L.marker([45.016582, -0.764977]).addTo(map)
        .bindPopup("TC Médullienne - Avensan (33480)");
}

// Carousel Logic
let currentSlide = 0;
const totalSlides = 3;

function showSlide(index) {
    const carouselInner = document.getElementById('carouselInner');
    if (carouselInner) {
        carouselInner.style.transform = `translateX(-${index * 100}%)`;
    }
}

function nextSlide() {
    currentSlide = (currentSlide + 1) % totalSlides;
    showSlide(currentSlide);
}

function prevSlide() {
    currentSlide = (currentSlide - 1 + totalSlides) % totalSlides;
    showSlide(currentSlide);
}

// Auto-advance carousel every 5 seconds
setInterval(nextSlide, 5000);

// Sponsor Rotation Logic
const sponsors = [
    { name: "Sponsor 1", url: "https://sponsor1.example.com", img: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 150 100'%3E%3Crect fill='%230077B6' width='150' height='100'/%3E%3Ctext x='75' y='50' text-anchor='middle' fill='white' font-size='12'%3ESponsor 1%3C/text%3E%3C/svg%3E" },
    { name: "Sponsor 2", url: "https://sponsor2.example.com", img: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 150 100'%3E%3Crect fill='%2300B4D8' width='150' height='100'/%3E%3Ctext x='75' y='50' text-anchor='middle' fill='white' font-size='12'%3ESponsor 2%3C/text%3E%3C/svg%3E" },
    { name: "Sponsor 3", url: "https://sponsor3.example.com", img: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 150 100'%3E%3Crect fill='%230096C7' width='150' height='100'/%3E%3Ctext x='75' y='50' text-anchor='middle' fill='white' font-size='12'%3ESponsor 3%3C/text%3E%3C/svg%3E" },
    { name: "Sponsor 4", url: "https://sponsor4.example.com", img: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 150 100'%3E%3Crect fill='%230077B6' width='150' height='100'/%3E%3Ctext x='75' y='50' text-anchor='middle' fill='white' font-size='12'%3ESponsor 4%3C/text%3E%3C/svg%3E" },
    { name: "Sponsor 5", url: "https://sponsor5.example.com", img: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 150 100'%3E%3Crect fill='%2300B4D8' width='150' height='100'/%3E%3Ctext x='75' y='50' text-anchor='middle' fill='white' font-size='12'%3ESponsor 5%3C/text%3E%3C/svg%3E" },
    { name: "Sponsor 6", url: "https://sponsor6.example.com", img: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 150 100'%3E%3Crect fill='%230096C7' width='150' height='100'/%3E%3Ctext x='75' y='50' text-anchor='middle' fill='white' font-size='12'%3ESponsor 6%3C/text%3E%3C/svg%3E" },
    { name: "Sponsor 7", url: "https://sponsor7.example.com", img: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 150 100'%3E%3Crect fill='%230077B6' width='150' height='100'/%3E%3Ctext x='75' y='50' text-anchor='middle' fill='white' font-size='12'%3ESponsor 7%3C/text%3E%3C/svg%3E" },
    { name: "Sponsor 8", url: "https://sponsor8.example.com", img: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 150 100'%3E%3Crect fill='%2300B4D8' width='150' height='100'/%3E%3Ctext x='75' y='50' text-anchor='middle' fill='white' font-size='12'%3ESponsor 8%3C/text%3E%3C/svg%3E" },
    { name: "Sponsor 9", url: "https://sponsor9.example.com", img: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 150 100'%3E%3Crect fill='%230096C7' width='150' height='100'/%3E%3Ctext x='75' y='50' text-anchor='middle' fill='white' font-size='12'%3ESponsor 9%3C/text%3E%3C/svg%3E" },
    { name: "Sponsor 10", url: "https://sponsor10.example.com", img: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 150 100'%3E%3Crect fill='%230077B6' width='150' height='100'/%3E%3Ctext x='75' y='50' text-anchor='middle' fill='white' font-size='12'%3ESponsor 10%3C/text%3E%3C/svg%3E" }
];

let currentSponsorIndex = 0;

function showSponsor(index) {
    const sponsor = sponsors[index];
    const sponsorLink = document.getElementById('sponsorLink');
    const sponsorImage = document.getElementById('sponsorImage');
    
    if (sponsorLink && sponsorImage) {
        sponsorLink.href = sponsor.url;
        sponsorImage.src = sponsor.img;
        sponsorImage.alt = sponsor.name;
    }
}

function nextSponsor() {
    currentSponsorIndex = (currentSponsorIndex + 1) % sponsors.length;
    showSponsor(currentSponsorIndex);
}

// Initialize sponsor display
showSponsor(currentSponsorIndex);

// Auto-advance sponsor every 3 seconds
setInterval(nextSponsor, 3000);

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
    document.getElementById('email-obfuscated').appendChild(emailLink);
});
