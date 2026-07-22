const path = require("path");
const webpack = require("webpack");
const HtmlWebpackPlugin = require("html-webpack-plugin");
const CopyWebpackPlugin = require("copy-webpack-plugin");
const devCerts = require("office-addin-dev-certs");

async function getHttpsOptions() {
  const httpsOptions = await devCerts.getHttpsServerOptions();
  return { ca: httpsOptions.ca, key: httpsOptions.key, cert: httpsOptions.cert };
}

module.exports = async (env, argv) => {
  const dev = argv.mode !== "production";
  // Dev: serve add-in over HTTPS and proxy hub calls same-origin to avoid mixed-content blocks
  // (https://localhost:3000 → http://hub). Override with HUB_PROXY_TARGET / HUB_BASE_URL.
  const hubProxyTarget =
    process.env.HUB_PROXY_TARGET ||
    process.env.HUB_BASE_URL ||
    "http://192.168.0.183:8000";
  // Dev default: same-origin relative URLs ("") so Office WebView uses the webpack
  // HTTPS proxy (/health, /v1 → hub) regardless of localhost vs 127.0.0.1.
  const hubPublicBase = process.env.HUB_PUBLIC_BASE_URL
    ? process.env.HUB_PUBLIC_BASE_URL
    : dev
      ? ""
      : hubProxyTarget;

  return {
    entry: {
      taskpane: ["./src/taskpane/index.tsx"],
    },
    output: {
      path: path.resolve(__dirname, "dist"),
      clean: true,
      filename: "[name].js",
    },
    resolve: {
      extensions: [".ts", ".tsx", ".html", ".js"],
    },
    module: {
      rules: [
        {
          test: /\.tsx?$/,
          exclude: /node_modules/,
          use: "ts-loader",
        },
        {
          test: /\.css$/,
          use: ["style-loader", "css-loader"],
        },
      ],
    },
    plugins: [
      new webpack.DefinePlugin({
        "process.env.HUB_BASE_URL": JSON.stringify(hubPublicBase),
      }),
      new HtmlWebpackPlugin({
        filename: "taskpane.html",
        template: "./src/taskpane/taskpane.html",
        chunks: ["taskpane"],
      }),
      new CopyWebpackPlugin({
        patterns: [
          { from: "assets", to: "assets", noErrorOnMissing: true },
          { from: "manifest.xml", to: "manifest.xml" },
        ],
      }),
    ],
    devServer: {
      static: { directory: path.join(__dirname, "dist") },
      headers: { "Access-Control-Allow-Origin": "*" },
      server: {
        type: "https",
        options: env.WEBPACK_BUILD || !dev ? {} : await getHttpsOptions(),
      },
      port: 3000,
      hot: true,
      proxy: [
        {
          context: ["/health", "/v1"],
          target: hubProxyTarget,
          changeOrigin: true,
          secure: false,
        },
      ],
    },
    devtool: dev ? "source-map" : false,
  };
};
