// Browser calls the backend on the same hostname, port 3333.
// Set this URL explicitly here when using a separate backend hostname.
const backendUrl = new URL(window.location.href);
backendUrl.port = '3333';
window.SURFACE_MAP_API_BASE_URL = backendUrl.origin;
