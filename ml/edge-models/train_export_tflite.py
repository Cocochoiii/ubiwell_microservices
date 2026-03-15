import json
from pathlib import Path

import numpy as np
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

OUTPUT_DIR = Path("apps/ios-edge-module/Resources/tflite")
MODEL_PATH = OUTPUT_DIR / "sensor_classifier.tflite"
SCALER_PATH = OUTPUT_DIR / "scaler.json"


def make_dataset(samples: int = 25000) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(7)
    hr = rng.normal(loc=82, scale=16, size=samples)
    spo2 = rng.normal(loc=96, scale=2.0, size=samples)
    motion = rng.normal(loc=0.25, scale=0.35, size=samples)
    X = np.vstack([hr, spo2, motion]).T.astype(np.float32)
    y = ((hr > 120) | (spo2 < 90) | (motion > 1.2)).astype(np.float32)
    return X, y.reshape(-1, 1)


def build_model(input_dim: int) -> tf.keras.Model:
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(input_dim,)),
            tf.keras.layers.Dense(16, activation="relu"),
            tf.keras.layers.Dense(8, activation="relu"),
            tf.keras.layers.Dense(1, activation="sigmoid"),
        ]
    )
    model.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])
    return model


def main() -> None:
    X, y = make_dataset()
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=7)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = build_model(input_dim=X_train_scaled.shape[1])
    model.fit(X_train_scaled, y_train, epochs=8, batch_size=128, verbose=0, validation_split=0.1)
    _, accuracy = model.evaluate(X_test_scaled, y_test, verbose=0)

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    tflite_model = converter.convert()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_bytes(tflite_model)
    SCALER_PATH.write_text(
        json.dumps(
            {
                "mean": scaler.mean_.tolist(),
                "scale": scaler.scale_.tolist(),
                "feature_order": ["heart_rate", "spo2", "motion_intensity"],
                "test_accuracy": round(float(accuracy), 4),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved model: {MODEL_PATH}")
    print(f"Saved scaler: {SCALER_PATH}")
    print(f"Validation accuracy: {accuracy:.4f}")


if __name__ == "__main__":
    main()
