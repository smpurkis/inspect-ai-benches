use burn::{
    nn::{
        Linear, LinearConfig, PaddingConfig2d, Relu,
        conv::{Conv2d, Conv2dConfig},
        pool::{MaxPool2d, MaxPool2dConfig},
    },
    prelude::{Backend, Module, Tensor},
};

#[derive(Module, Debug)]
pub struct CifarModel<B: Backend> {
    conv1: Conv2d<B>,
    conv2: Conv2d<B>,
    pool: MaxPool2d,
    classifier: Linear<B>,
    activation: Relu,
}

impl<B: Backend> CifarModel<B> {
    pub fn new(device: &B::Device) -> Self {
        Self {
            conv1: Conv2dConfig::new([3, 32], [3, 3])
                .with_padding(PaddingConfig2d::Same)
                .init(device),
            conv2: Conv2dConfig::new([32, 64], [3, 3])
                .with_padding(PaddingConfig2d::Same)
                .init(device),
            pool: MaxPool2dConfig::new([2, 2]).with_strides([2, 2]).init(),
            classifier: LinearConfig::new(64 * 8 * 8, 10).init(device),
            activation: Relu::new(),
        }
    }

    #[allow(dead_code)]
    pub fn forward(&self, images: Tensor<B, 4>) -> Tensor<B, 2> {
        let x = self.pool.forward(self.activation.forward(self.conv1.forward(images)));
        let x = self.pool.forward(self.activation.forward(self.conv2.forward(x)));
        let [batch, channels, height, width] = x.dims();
        self.classifier
            .forward(x.reshape([batch, channels * height * width]))
    }
}
