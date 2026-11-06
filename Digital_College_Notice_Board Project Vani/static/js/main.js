
// ======================================
// 1. HOMEPAGE SEARCH
// ======================================

const homeSearch = document.getElementById("searchInput");

function searchNotices() {

    const noticeContainer = document.getElementById("noticeContainer");

    if (!homeSearch || !noticeContainer) {
        return;
    }

    const searchText = homeSearch.value.toLowerCase();

    const noticeCards = noticeContainer.querySelectorAll(".notice-card");

    noticeCards.forEach(function(card) {

        const cardText = card.innerText.toLowerCase();

        if (cardText.includes(searchText)) {
            card.style.display = "";
        } else {
            card.style.display = "none";
        }

    });
}

if (homeSearch) {
    homeSearch.addEventListener("input", searchNotices);
}


// ======================================
// 2. EVENTS PAGE SEARCH AND FILTER
// ======================================

const eventSearch = document.getElementById("eventSearch");

if (eventSearch) {

    const filterButtons = document.querySelectorAll(
        ".event-filters .filter-btn"
    );

    const eventCards = document.querySelectorAll(".event-card");

    const noEvents = document.getElementById("noEvents");

    let selectedCategory = "all";

    function filterEvents() {

        const searchText = eventSearch.value.toLowerCase();

        let visibleCount = 0;

        eventCards.forEach(function(card) {

            const category = card.dataset.category;

            const cardText = card.innerText.toLowerCase();

            const matchesCategory =
                selectedCategory === "all" ||
                category === selectedCategory;

            const matchesSearch =
                cardText.includes(searchText);

            if (matchesCategory && matchesSearch) {

                card.style.display = "flex";
                visibleCount++;

            } else {

                card.style.display = "none";

            }

        });

        if (noEvents) {
            noEvents.style.display =
                visibleCount === 0 ? "block" : "none";
        }
    }

    eventSearch.addEventListener("input", filterEvents);

    filterButtons.forEach(function(button) {

        button.addEventListener("click", function() {

            filterButtons.forEach(function(btn) {
                btn.classList.remove("active");
            });

            button.classList.add("active");

            selectedCategory = button.dataset.category;

            filterEvents();

        });

    });

}


// ======================================
// 3. ACADEMICS PAGE SEARCH AND FILTER
// ======================================

const academicSearch = document.getElementById("academicSearch");

if (academicSearch) {

    const academicButtons =
        document.querySelectorAll(".academic-filter");

    const academicCards =
        document.querySelectorAll(".academic-card");

    const noAcademicNotices =
        document.getElementById("noAcademicNotices");

    let selectedAcademicCategory = "all";

    function filterAcademicNotices() {

        const searchText = academicSearch.value.toLowerCase();

        let visibleCount = 0;

        academicCards.forEach(function(card) {

            const category = card.dataset.category;

            const cardText = card.innerText.toLowerCase();

            const matchesCategory =
                selectedAcademicCategory === "all" ||
                category === selectedAcademicCategory;

            const matchesSearch =
                cardText.includes(searchText);

            if (matchesCategory && matchesSearch) {

                card.style.display = "flex";
                visibleCount++;

            } else {

                card.style.display = "none";

            }

        });

        if (noAcademicNotices) {
            noAcademicNotices.style.display =
                visibleCount === 0 ? "block" : "none";
        }
    }

    academicSearch.addEventListener(
        "input",
        filterAcademicNotices
    );

    academicButtons.forEach(function(button) {

        button.addEventListener("click", function() {

            academicButtons.forEach(function(btn) {
                btn.classList.remove("active");
            });

            button.classList.add("active");

            selectedAcademicCategory = button.dataset.category;

            filterAcademicNotices();

        });

    });

}


// ======================================
// 4. ANNOUNCEMENTS PAGE SEARCH AND FILTER
// ======================================

const announcementSearch =
    document.getElementById("announcementSearch");

if (announcementSearch) {

    const announcementButtons =
        document.querySelectorAll(".announcement-filter");

    const announcementCards =
        document.querySelectorAll(".announcement-card");

    const noAnnouncements =
        document.getElementById("noAnnouncements");

    let selectedAnnouncementCategory = "all";

    function filterAnnouncements() {

        const searchText =
            announcementSearch.value.toLowerCase();

        let visibleCount = 0;

        announcementCards.forEach(function(card) {

            const category = card.dataset.category;

            const cardText = card.innerText.toLowerCase();

            const matchesCategory =
                selectedAnnouncementCategory === "all" ||
                category === selectedAnnouncementCategory;

            const matchesSearch =
                cardText.includes(searchText);

            if (matchesCategory && matchesSearch) {

                card.style.display = "flex";
                visibleCount++;

            } else {

                card.style.display = "none";

            }

        });

        if (noAnnouncements) {
            noAnnouncements.style.display =
                visibleCount === 0 ? "block" : "none";
        }
    }

    announcementSearch.addEventListener(
        "input",
        filterAnnouncements
    );

    announcementButtons.forEach(function(button) {

        button.addEventListener("click", function() {

            announcementButtons.forEach(function(btn) {
                btn.classList.remove("active");
            });

            button.classList.add("active");

            selectedAnnouncementCategory =
                button.dataset.category;

            filterAnnouncements();

        });

    });

}

/* =========================================
   MOBILE NAVIGATION MENU
========================================= */

const menuToggle = document.getElementById("menuToggle");
const mainNavbar = document.getElementById("mainNavbar");
const header = document.querySelector(".header");

if (menuToggle && mainNavbar && header) {

    // Open and close menu
    menuToggle.addEventListener("click", function () {

        const isOpen = header.classList.toggle("menu-open");

        menuToggle.classList.toggle("active", isOpen);

        menuToggle.setAttribute("aria-expanded", isOpen);

        menuToggle.setAttribute(
            "aria-label",
            isOpen ? "Close navigation menu" : "Open navigation menu"
        );
    });

    // Close menu after clicking a navigation link
    mainNavbar.querySelectorAll("a").forEach(function (link) {

        link.addEventListener("click", function () {

            header.classList.remove("menu-open");
            menuToggle.classList.remove("active");

            menuToggle.setAttribute("aria-expanded", "false");
            menuToggle.setAttribute("aria-label", "Open navigation menu");

        });

    });

    // Close menu using Escape key
    document.addEventListener("keydown", function (event) {

        if (event.key === "Escape") {

            header.classList.remove("menu-open");
            menuToggle.classList.remove("active");

            menuToggle.setAttribute("aria-expanded", "false");
            menuToggle.setAttribute("aria-label", "Open navigation menu");

        }

    });

}

/* LIVE CAMPUS CLOCK */

const greetingText = document.getElementById("greetingText");
const liveDate = document.getElementById("liveDate");
const liveTime = document.getElementById("liveTime");

function updateCampusClock() {

    // Get the current date and time
    const now = new Date();

    // Display the date
    if (liveDate) {
        liveDate.textContent = now.toLocaleDateString("en-IN", {
            weekday: "long",
            day: "numeric",
            month: "long",
            year: "numeric"
        });
    }

    // Display the live time
    if (liveTime) {
        liveTime.textContent = now.toLocaleTimeString("en-IN", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: true
        });
    }

    // Change greeting according to the time
    if (greetingText) {
        const hour = now.getHours();

        if (hour >= 5 && hour < 12) {
            greetingText.textContent = "Good Morning! ☀️";
        } else if (hour >= 12 && hour < 17) {
            greetingText.textContent = "Good Afternoon! 🌤️";
        } else {
            greetingText.textContent = "Good Evening! 🌙";
        }
    }
}

// Run immediately and update every second
if (liveDate && liveTime && greetingText) {
    updateCampusClock();
    setInterval(updateCampusClock, 1000);
}

/* SCROLL REVEAL ANIMATION */

document.addEventListener("DOMContentLoaded", function () {

    const revealElements = document.querySelectorAll(
        ".hero-content, .clock-card, .section-heading, " +
        ".category-card, .notice-card, .cta-section, " +
        ".event-card, .academic-card, .announcement-card"
    );

    // Show everything immediately if animations are disabled
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        revealElements.forEach(function (element) {
            element.classList.add("active");
        });
        return;
    }

    // Reveal elements as they enter the screen
    const observer = new IntersectionObserver(function (entries, observer) {

        entries.forEach(function (entry) {

            if (entry.isIntersecting) {
                entry.target.classList.add("active");
                observer.unobserve(entry.target);
            }

        });

    }, {
        threshold: 0.12
    });

    revealElements.forEach(function (element) {
        element.classList.add("reveal");
        observer.observe(element);
    });

});

/* 3D CARD TILT EFFECT */

if (window.matchMedia("(hover: hover) and (pointer: fine)").matches &&
    !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {

    const tiltCards = document.querySelectorAll(
        ".category-card, .notice-card, .event-card, " +
        ".academic-card, .announcement-card"
    );

    tiltCards.forEach(function (card) {

        card.addEventListener("mousemove", function (event) {

            const rect = card.getBoundingClientRect();

            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;

            const centerX = rect.width / 2;
            const centerY = rect.height / 2;

            const rotateX = ((y - centerY) / centerY) * -3;
            const rotateY = ((x - centerX) / centerX) * 3;

            card.style.transform =
                `perspective(800px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
        });

        card.addEventListener("mouseleave", function () {
            card.style.transform = "";
        });

    });
}

/* HERO TYPING ANIMATION */

document.addEventListener("DOMContentLoaded", function () {

    const typingText = document.getElementById("typingText");

    if (!typingText) return;

    // Phrases to display
    const phrases = [
        "Discover Campus Events",
        "Explore Hackathons",
        "Find Workshops",
        "Stay Updated"
    ];

    // Respect reduced-motion preferences
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        typingText.textContent = phrases[0];
        return;
    }

    let phraseIndex = 0;
    let characterIndex = 0;
    let deleting = false;

    function typeEffect() {

        const currentPhrase = phrases[phraseIndex];

        if (!deleting) {

            typingText.textContent =
                currentPhrase.substring(0, characterIndex + 1);

            characterIndex++;

            if (characterIndex === currentPhrase.length) {
                deleting = true;
                setTimeout(typeEffect, 1500);
                return;
            }

        } else {

            typingText.textContent =
                currentPhrase.substring(0, characterIndex - 1);

            characterIndex--;

            if (characterIndex === 0) {
                deleting = false;
                phraseIndex = (phraseIndex + 1) % phrases.length;
            }

        }

        setTimeout(typeEffect, deleting ? 45 : 85);
    }

    typeEffect();

});

