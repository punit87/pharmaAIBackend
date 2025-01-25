export default {
  async fetch(request, env, ctx) {
    // Get the request URL
    const url = new URL(request.url);
    
    // Define the base API endpoints to disable caching for (ignoring query parameters)
    const noCacheBaseUrls = [
      'https://3xlzgm0kf5.execute-api.us-east-2.amazonaws.com/dev/test-model',
      'https://15e618qft3.execute-api.us-east-2.amazonaws.com/dev/gen-sec-resp'
    ];
    
    // Check if the request URL's base URL matches any of the no-cache APIs (ignores query params)
    const baseUrl = url.origin + url.pathname;  // Construct base URL without query params

    if (noCacheBaseUrls.some(noCacheUrl => baseUrl.startsWith(noCacheUrl))) {
      // Create the response
      const response = await fetch(request);

      // Modify the response headers to disable caching
      const modifiedResponse = new Response(response.body, response);
      modifiedResponse.headers.set('Cache-Control', 'no-cache, no-store, must-revalidate');
      modifiedResponse.headers.set('Pragma', 'no-cache');  // For older HTTP/1.0 caches
      modifiedResponse.headers.set('Expires', '0');  // Ensure that responses are not cached

      // Return the modified response
      return modifiedResponse;
    }

    // If the request is not for one of the no-cache APIs, return the default response (or pass it through)
    return fetch(request);
  }
};
