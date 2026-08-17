module.exports = {
  default: {
    requireModule: ["ts-node/register"],
    require: ["step-definitions/**/*.ts"],
    paths: ["features/**/*.feature"],
    format: ["progress-bar"],
  },
};
