module.exports = {
  preset: "ts-jest",
  testEnvironment: "node",
  roots: ["<rootDir>/src"],
  testMatch: ["**/*.test.ts"],
  collectCoverage: true,
  collectCoverageFrom: ["src/lib/**/*.ts"],
  coverageDirectory: "../../docs/perf/results/jest-coverage",
  coverageReporters: ["json-summary", "text", "lcov"],
  coverageThreshold: {
    global: {
      statements: 92,
      branches: 85,
      functions: 92,
      lines: 92
    }
  }
};
