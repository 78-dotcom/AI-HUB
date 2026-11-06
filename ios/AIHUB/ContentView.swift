import SwiftUI
import WebKit
import UIKit

private let appHost = "ai-hub-w6h6.onrender.com"
private let appURL = URL(string: "https://ai-hub-w6h6.onrender.com/")!

struct ContentView: View {
    @State private var loadError: String?
    @State private var reloadToken = UUID()

    var body: some View {
        ZStack {
            Color(red: 0.06, green: 0.075, blue: 0.105).ignoresSafeArea()
            AIHUBWebView(loadError: $loadError, reloadToken: reloadToken)
                .ignoresSafeArea(.container, edges: .bottom)

            if let loadError {
                VStack(spacing: 14) {
                    Image(systemName: "wifi.exclamationmark")
                        .font(.system(size: 34))
                    Text("AI HUB couldn't connect")
                        .font(.headline)
                    Text(loadError)
                        .font(.footnote)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                    Button("Try again") {
                        self.loadError = nil
                        reloadToken = UUID()
                    }
                    .buttonStyle(.borderedProminent)
                }
                .padding(24)
                .frame(maxWidth: 340)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 20))
                .padding()
            }
        }
        .statusBarHidden(false)
    }
}

private struct AIHUBWebView: UIViewRepresentable {
    @Binding var loadError: String?
    let reloadToken: UUID

    func makeCoordinator() -> Coordinator {
        Coordinator(loadError: $loadError, reloadToken: reloadToken)
    }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.contentInsetAdjustmentBehavior = .automatic
        webView.isOpaque = false
        webView.backgroundColor = UIColor(red: 0.06, green: 0.075, blue: 0.105, alpha: 1)
        webView.scrollView.backgroundColor = webView.backgroundColor
        webView.load(URLRequest(url: appURL, cachePolicy: .useProtocolCachePolicy, timeoutInterval: 30))
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        if context.coordinator.lastReloadToken != reloadToken {
            context.coordinator.lastReloadToken = reloadToken
            webView.load(URLRequest(url: appURL, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30))
        }
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        @Binding private var loadError: String?
        var lastReloadToken: UUID

        init(loadError: Binding<String?>, reloadToken: UUID) {
            _loadError = loadError
            lastReloadToken = reloadToken
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = navigationAction.request.url,
                  let scheme = url.scheme?.lowercased() else {
                decisionHandler(.cancel)
                return
            }

            guard scheme == "https" else {
                decisionHandler(.cancel)
                return
            }

            if url.host?.lowercased() == appHost && (url.port == nil || url.port == 443) {
                decisionHandler(.allow)
            } else {
                UIApplication.shared.open(url)
                decisionHandler(.cancel)
            }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            loadError = nil
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!,
                     withError error: Error) {
            loadError = error.localizedDescription
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!,
                     withError error: Error) {
            loadError = error.localizedDescription
        }

        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                     for navigationAction: WKNavigationAction,
                     windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let url = navigationAction.request.url, url.scheme?.lowercased() == "https" {
                UIApplication.shared.open(url)
            }
            return nil
        }
    }
}
