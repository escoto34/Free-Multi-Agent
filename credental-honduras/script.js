document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('contact-form');
    const successMessage = document.getElementById('success-message');

    form.addEventListener('submit', function(e) {
        e.preventDefault();

        // Simulate form submission
        setTimeout(function() {
            form.reset();
            successMessage.style.display = 'block';

            // Hide the success message after 5 seconds
            setTimeout(function() {
                successMessage.style.display = 'none';
            }, 5000);
        }, 1000);
    });
});
