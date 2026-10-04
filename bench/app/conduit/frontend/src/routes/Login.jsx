import { useState } from "react";
import AuthPageContainer from "../components/AuthPageContainer";
import LoginForm from "../components/LoginForm";
import { bug } from "../helpers/bugs";

function Login() {
  const [errorMessage, setErrorMessage] = useState();

  const handleError = (error) => {
    if (bug("login-error-hidden")) return; // [testomation bug]
    setErrorMessage(error);
  };

  return (
    <AuthPageContainer
      error={errorMessage}
      path="/register"
      text="Need an account?"
      title="Sign in"
    >
      <LoginForm onError={handleError} />
    </AuthPageContainer>
  );
}

export default Login;
